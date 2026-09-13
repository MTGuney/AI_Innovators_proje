namespace FinAi.Api.Entities;

/// <summary>How far a report has progressed through the AI service's index.</summary>
public enum IndexStatus
{
    Pending = 0,
    Indexed = 1,
    Duplicate = 2,
    Failed = 3
}

/// <summary>
/// Metadata for one financial report. The document text and its embeddings live
/// in ChromaDB, owned by the AI service; <see cref="DocumentId"/> is the link
/// between the two stores.
/// </summary>
public class FinancialReport
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public Guid CompanyId { get; set; }

    public Company? Company { get; set; }

    public string Title { get; set; } = string.Empty;

    public int? Year { get; set; }

    public string ReportType { get; set; } = "10-K";

    public string FileName { get; set; } = string.Empty;

    /// <summary>Identifier of the corresponding document in the vector index.</summary>
    public string? DocumentId { get; set; }

    public IndexStatus IndexStatus { get; set; } = IndexStatus.Pending;

    public string? IndexMessage { get; set; }

    public int PageCount { get; set; }

    public int ChunkCount { get; set; }

    public long FileSizeBytes { get; set; }

    public DateTime UploadedAt { get; set; } = DateTime.UtcNow;
}
