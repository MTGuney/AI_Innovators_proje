namespace FinAi.Api.Entities;

/// <summary>A chat thread between a user and the assistant.</summary>
public class Conversation
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public Guid UserId { get; set; }

    public User? User { get; set; }

    /// <summary>Derived from the first question so the sidebar reads sensibly.</summary>
    public string Title { get; set; } = "New conversation";

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<Message> Messages { get; set; } = new List<Message>();
}
