namespace FinRag.Api.Entities;

public enum MessageRole
{
    User = 0,
    Assistant = 1
}

/// <summary>One turn in a conversation, with the evidence behind it.</summary>
public class Message
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public Guid ConversationId { get; set; }

    public Conversation? Conversation { get; set; }

    public MessageRole Role { get; set; }

    public string Content { get; set; } = string.Empty;

    /// <summary>
    /// Citations serialised as JSON. Stored verbatim so a past answer always
    /// renders with the exact sources it was produced from, even after the
    /// index is rebuilt.
    /// </summary>
    public string? SourcesJson { get; set; }

    public string? KeyPointsJson { get; set; }

    /// <summary>
    /// Figures the AI service could not locate in the retrieved passages,
    /// serialised as JSON. Stored so a caveat shown at the time is not lost
    /// when the conversation is reopened.
    /// </summary>
    public string? UnsupportedFiguresJson { get; set; }

    public string? Confidence { get; set; }

    public bool Grounded { get; set; } = true;

    public int? ElapsedMs { get; set; }

    public string? Model { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
}
