using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using FinRag.Api.Configuration;
using FinRag.Api.DTOs;
using FinRag.Api.Entities;
using FinRag.Api.Repositories;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;

namespace FinRag.Api.Services;

/// <summary>Raised for expected, user-correctable problems.</summary>
public class DomainException(string message, int statusCode = 400) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
}

public interface IAuthService
{
    Task<AuthResponse> RegisterAsync(RegisterRequest request, CancellationToken ct = default);

    Task<AuthResponse> LoginAsync(LoginRequest request, CancellationToken ct = default);
}

public class AuthService(
    IUserRepository users,
    IOptions<JwtOptions> jwtOptions,
    ILogger<AuthService> logger) : IAuthService
{
    private readonly JwtOptions _jwt = jwtOptions.Value;

    public async Task<AuthResponse> RegisterAsync(
        RegisterRequest request, CancellationToken ct = default)
    {
        var email = request.Email.Trim().ToLowerInvariant();
        if (await users.ExistsAsync(email, ct))
        {
            throw new DomainException("An account with this email already exists.", 409);
        }

        var user = await users.AddAsync(
            new User
            {
                Email = email,
                DisplayName = request.DisplayName.Trim(),
                PasswordHash = BCrypt.Net.BCrypt.HashPassword(request.Password)
            },
            ct);

        logger.LogInformation("Registered new user {UserId}.", user.Id);
        return BuildResponse(user);
    }

    public async Task<AuthResponse> LoginAsync(
        LoginRequest request, CancellationToken ct = default)
    {
        var user = await users.GetByEmailAsync(request.Email.Trim(), ct);

        // Identical message and work for both failure modes, so the response
        // does not reveal whether an account exists.
        if (user is null || !BCrypt.Net.BCrypt.Verify(request.Password, user.PasswordHash))
        {
            logger.LogWarning("Failed login attempt.");
            throw new DomainException("Invalid email or password.", 401);
        }

        return BuildResponse(user);
    }

    private AuthResponse BuildResponse(User user)
    {
        var expiresAt = DateTime.UtcNow.AddMinutes(_jwt.ExpiryMinutes);
        var credentials = new SigningCredentials(
            new SymmetricSecurityKey(Encoding.UTF8.GetBytes(_jwt.Secret)),
            SecurityAlgorithms.HmacSha256);

        var token = new JwtSecurityToken(
            issuer: _jwt.Issuer,
            audience: _jwt.Audience,
            claims:
            [
                new Claim(JwtRegisteredClaimNames.Sub, user.Id.ToString()),
                new Claim(JwtRegisteredClaimNames.Email, user.Email),
                new Claim(JwtRegisteredClaimNames.Jti, Guid.NewGuid().ToString()),
                new Claim("name", user.DisplayName)
            ],
            expires: expiresAt,
            signingCredentials: credentials);

        return new AuthResponse(
            new JwtSecurityTokenHandler().WriteToken(token),
            expiresAt,
            new UserDto(user.Id, user.Email, user.DisplayName));
    }
}
