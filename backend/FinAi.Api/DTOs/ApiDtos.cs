using System.ComponentModel.DataAnnotations;

namespace FinAi.Api.DTOs;

// --------------------------------------------------------------------- //
// Reports
// --------------------------------------------------------------------- //

public record ReportDto(
    Guid Id,
    string Title,
    string CompanyName,
    string? Ticker,
    int? Year,
    string ReportType,
    string FileName,
    string? DocumentId,
    string IndexStatus,
    int PageCount,
    int ChunkCount,
    long FileSizeBytes,
    DateTime UploadedAt);

/// <summary>A page of reports, so the UI can page rather than load everything.</summary>
public record PagedResult<T>(IReadOnlyList<T> Items, int Total, int Page, int PageSize);

public record ReportQuery(
    string? Search = null,
    string? Company = null,
    int? Year = null,
    string? ReportType = null,
    int Page = 1,
    int PageSize = 20);

public record UploadReportResponse(ReportDto Report, AiIngestResult Indexing);

// --------------------------------------------------------------------- //
// Chat
// --------------------------------------------------------------------- //

public record ChatRequest(
    [Required, MinLength(3), MaxLength(2000)] string Question,
    Guid? ConversationId = null,
    List<string>? Companies = null,
    List<int>? Years = null,
    List<string>? ReportTypes = null,
    List<string>? DocumentIds = null,
    int? TopK = null);

public record ChatResponse(
    Guid ConversationId,
    Guid MessageId,
    string Answer,
    List<string> KeyPoints,
    List<SourceCitation> Sources,
    List<RetrievedChunk> RetrievedChunks,
    string Confidence,
    bool Grounded,
    List<string> UnsupportedFigures,
    string Model,
    int ElapsedMs,
    DateTime CreatedAt);

public record MessageDto(
    Guid Id,
    string Role,
    string Content,
    List<string> KeyPoints,
    List<SourceCitation> Sources,
    string? Confidence,
    bool Grounded,
    List<string> UnsupportedFigures,
    int? ElapsedMs,
    string? Model,
    DateTime CreatedAt);

public record ConversationSummaryDto(
    Guid Id,
    string Title,
    int MessageCount,
    DateTime CreatedAt,
    DateTime UpdatedAt);

public record ConversationDetailDto(
    Guid Id,
    string Title,
    DateTime CreatedAt,
    DateTime UpdatedAt,
    List<MessageDto> Messages);

// --------------------------------------------------------------------- //
// Index
// --------------------------------------------------------------------- //

public record IndexStatusDto(
    bool AiServiceHealthy,
    string? AiServiceDetail,
    int IndexedDocuments,
    int IndexedChunks);

// --------------------------------------------------------------------- //
// Errors
// --------------------------------------------------------------------- //

/// <summary>Uniform error envelope. Never carries stack traces.</summary>
public record ApiError(string Error, string? Detail = null);
