namespace FinRag.Api.Configuration;

/// <summary>Token issuing and validation settings.</summary>
public class JwtOptions
{
    public const string SectionName = "Jwt";

    /// <summary>Must be at least 32 characters; supplied via configuration only.</summary>
    public string Secret { get; set; } = string.Empty;

    public string Issuer { get; set; } = "finrag-api";

    public string Audience { get; set; } = "finrag-web";

    public int ExpiryMinutes { get; set; } = 720;
}
