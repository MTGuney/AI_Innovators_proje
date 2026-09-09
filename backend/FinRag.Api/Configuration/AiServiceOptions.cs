namespace FinRag.Api.Configuration;

/// <summary>Connection settings for the Python RAG service.</summary>
public class AiServiceOptions
{
    public const string SectionName = "AiService";

    public string BaseUrl { get; set; } = "http://localhost:8000";

    /// <summary>
    /// Generous by default: a local LLM answering from a long context can take
    /// tens of seconds on modest hardware.
    /// </summary>
    public int TimeoutSeconds { get; set; } = 240;
}
