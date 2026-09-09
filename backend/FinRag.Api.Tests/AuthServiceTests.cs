using System.IdentityModel.Tokens.Jwt;
using FinRag.Api.Configuration;
using FinRag.Api.Data;
using FinRag.Api.DTOs;
using FinRag.Api.Repositories;
using FinRag.Api.Services;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace FinRag.Api.Tests;

public class AuthServiceTests : IDisposable
{
    private readonly FinRagDbContext _db;
    private readonly AuthService _auth;

    public AuthServiceTests()
    {
        var options = new DbContextOptionsBuilder<FinRagDbContext>()
            .UseInMemoryDatabase($"auth-{Guid.NewGuid()}")
            .Options;
        _db = new FinRagDbContext(options);

        _auth = new AuthService(
            new UserRepository(_db),
            Options.Create(new JwtOptions
            {
                Secret = "test-secret-that-is-long-enough-for-hmac-256",
                Issuer = "finrag-api",
                Audience = "finrag-web",
                ExpiryMinutes = 60
            }),
            NullLogger<AuthService>.Instance);
    }

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task RegisterAsync_IssuesATokenCarryingTheUserId()
    {
        var response = await _auth.RegisterAsync(
            new RegisterRequest("Analyst@Example.com", "password123", "Analyst"));

        var token = new JwtSecurityTokenHandler().ReadJwtToken(response.Token);
        var subject = token.Claims.Single(claim => claim.Type == JwtRegisteredClaimNames.Sub);

        Assert.Equal(response.User.Id.ToString(), subject.Value);
        // Emails are normalised so casing cannot create duplicate accounts.
        Assert.Equal("analyst@example.com", response.User.Email);
    }

    [Fact]
    public async Task RegisterAsync_NeverStoresThePlaintextPassword()
    {
        await _auth.RegisterAsync(new RegisterRequest("a@b.com", "password123", "A"));

        var user = await _db.Users.SingleAsync();
        Assert.NotEqual("password123", user.PasswordHash);
        Assert.StartsWith("$2", user.PasswordHash);
    }

    [Fact]
    public async Task RegisterAsync_RejectsADuplicateEmail()
    {
        await _auth.RegisterAsync(new RegisterRequest("a@b.com", "password123", "A"));

        var error = await Assert.ThrowsAsync<DomainException>(
            () => _auth.RegisterAsync(new RegisterRequest("A@B.com", "password123", "A")));

        Assert.Equal(409, error.StatusCode);
    }

    [Fact]
    public async Task LoginAsync_SucceedsWithCorrectCredentials()
    {
        await _auth.RegisterAsync(new RegisterRequest("a@b.com", "password123", "A"));

        var response = await _auth.LoginAsync(new LoginRequest("a@b.com", "password123"));

        Assert.False(string.IsNullOrWhiteSpace(response.Token));
        Assert.True(response.ExpiresAt > DateTime.UtcNow);
    }

    [Theory]
    [InlineData("a@b.com", "wrong-password")]
    [InlineData("missing@b.com", "password123")]
    public async Task LoginAsync_GivesTheSameErrorForBadPasswordAndUnknownUser(
        string email, string password)
    {
        await _auth.RegisterAsync(new RegisterRequest("a@b.com", "password123", "A"));

        var error = await Assert.ThrowsAsync<DomainException>(
            () => _auth.LoginAsync(new LoginRequest(email, password)));

        // Identical responses stop the endpoint being used to enumerate accounts.
        Assert.Equal(401, error.StatusCode);
        Assert.Equal("Invalid email or password.", error.Message);
    }
}
