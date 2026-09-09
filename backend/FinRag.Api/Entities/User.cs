namespace FinRag.Api.Entities;

/// <summary>An authenticated user of the research assistant.</summary>
public class User
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public string Email { get; set; } = string.Empty;

    public string DisplayName { get; set; } = string.Empty;

    /// <summary>BCrypt hash. The plaintext password is never stored or logged.</summary>
    public string PasswordHash { get; set; } = string.Empty;

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<Conversation> Conversations { get; set; } = new List<Conversation>();
}
