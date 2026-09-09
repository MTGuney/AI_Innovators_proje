using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;

namespace FinRag.Api.Extensions;

public static class ClaimsPrincipalExtensions
{
    /// <summary>
    /// The authenticated user's id. Controllers are already behind
    /// <c>[Authorize]</c>, so a missing or malformed subject claim means the
    /// token was issued incorrectly -- fail loudly rather than guess.
    /// </summary>
    public static Guid GetUserId(this ClaimsPrincipal principal)
    {
        var subject = principal.FindFirstValue(JwtRegisteredClaimNames.Sub)
                      ?? principal.FindFirstValue(ClaimTypes.NameIdentifier);

        return Guid.TryParse(subject, out var userId)
            ? userId
            : throw new InvalidOperationException("The access token carries no valid user id.");
    }
}
