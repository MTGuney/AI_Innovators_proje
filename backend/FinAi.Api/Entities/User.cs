namespace FinAi.Api.Entities;

/// <summary>
/// The owner of a conversation. FinAI runs as a single local user with no
/// sign-in, so in practice exactly one of these exists.
/// </summary>
public class User
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public string Email { get; set; } = string.Empty;

    public string DisplayName { get; set; } = string.Empty;

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<Conversation> Conversations { get; set; } = new List<Conversation>();
}
