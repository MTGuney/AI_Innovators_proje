namespace FinAi.Api.DTOs;

/// <summary>
/// Mirrors the Python AI service's HTTP contract (app/models/schemas.py).
/// Serialisation uses snake_case to match it; see AiServiceClient.
/// Changing these types is a breaking change on both sides.
/// </summary>
public record RetrievalFilters(
    List<string>? Companies = null,
    List<int>? Years = null,
    List<string>? ReportTypes = null,
    List<string>? DocumentIds = null);

public record ChatTurn(string Role, string Content);

public record RagQueryRequest(
    string Question,
    int? TopK = null,
    double? SimilarityThreshold = null,
    RetrievalFilters? Filters = null,
    List<ChatTurn>? History = null);

public record SourceCitation(
    string Document,
    string DocumentId,
    int? Page,
    double Relevance,
    string? Company,
    int? Year,
    string? ReportType,
    string? Section,
    string ChunkId,
    string Excerpt);

public record RetrievedChunk(
    string ChunkId,
    string DocumentId,
    string SourceFile,
    string? Company,
    int? Year,
    string? ReportType,
    string? Title,
    string? Section,
    int? PageNumber,
    int? ChunkIndex,
    double Relevance,
    string Text);

public record RagAnswer(
    string Answer,
    List<string> KeyPoints,
    List<SourceCitation> Sources,
    string Confidence,
    bool Grounded,
    string Model,
    int ElapsedMs,
    List<RetrievedChunk> RetrievedChunks,
    List<string> UnsupportedFigures);

public record SearchRequest(
    string Question,
    int? TopK = null,
    double? SimilarityThreshold = null,
    RetrievalFilters? Filters = null);

public record SearchResponse(
    string Question,
    int TopK,
    double SimilarityThreshold,
    int TotalCandidates,
    List<RetrievedChunk> Chunks);

public record ComparisonRequest(
    List<string> Companies,
    string Metric,
    List<int>? Years = null,
    int? TopKPerCompany = null);

public record CompanyFindings(
    string Company,
    string Kind,
    List<string> Findings,
    List<SourceCitation> Sources,
    bool HasData);

public record ComparisonResponse(
    string Metric,
    List<string> Companies,
    List<int> Years,
    List<CompanyFindings> PerCompany,
    string Summary,
    string SummaryKind,
    string Confidence,
    List<string> UnsupportedFigures,
    string Model,
    int ElapsedMs);

public record AiIngestRequest(
    string Path,
    string? Company = null,
    int? Year = null,
    string? ReportType = null,
    string? Title = null,
    string? DocumentId = null,
    bool Force = false);

public record AiIngestResult(
    string DocumentId,
    string SourceFile,
    string Status,
    int ChunkCount,
    int PageCount,
    int CharCount,
    string? Company,
    int? Year,
    string? ReportType,
    string? Title,
    string? Message);

public record IndexedDocument(
    string DocumentId,
    string? SourceFile,
    string? Title,
    string? Company,
    int? Year,
    string? ReportType,
    int ChunkCount,
    int PageCount);

public record IndexStats(
    int TotalDocuments,
    int TotalChunks,
    List<string> Companies,
    List<int> Years,
    List<string> ReportTypes,
    Dictionary<string, int> DocumentsByYear);

public record ComponentHealth(string Name, bool Healthy, string? Detail);

public record AiHealthResponse(
    string Status,
    string Service,
    List<ComponentHealth> Components,
    string ChatModel,
    string EmbeddingModel);

/// <summary>The AI service's uniform error envelope.</summary>
public record AiErrorResponse(string Error, string? Detail);
