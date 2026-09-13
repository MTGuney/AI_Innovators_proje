using FinAi.Api.DTOs;
using FinAi.Api.Entities;
using FinAi.Api.Repositories;

namespace FinAi.Api.Services;

public interface IReportService
{
    Task<PagedResult<ReportDto>> GetReportsAsync(ReportQuery query, CancellationToken ct = default);

    Task<ReportDto?> GetReportAsync(Guid id, CancellationToken ct = default);

    Task<UploadReportResponse> UploadAsync(
        IFormFile file,
        string? company,
        int? year,
        string? reportType,
        string? title,
        CancellationToken ct = default);

    Task DeleteAsync(Guid id, CancellationToken ct = default);

    /// <summary>Import reports the AI service already has indexed, so a corpus
    /// seeded by the CLI shows up in the catalogue without re-uploading.</summary>
    Task<int> SyncFromIndexAsync(CancellationToken ct = default);
}

public class ReportService(
    IReportRepository reports,
    ICompanyRepository companies,
    IAiServiceClient aiService,
    IWebHostEnvironment environment,
    ILogger<ReportService> logger) : IReportService
{
    private static readonly string[] AllowedExtensions = [".pdf", ".txt", ".md", ".html", ".htm"];

    private const long MaxUploadBytes = 64L * 1024 * 1024;

    public async Task<PagedResult<ReportDto>> GetReportsAsync(
        ReportQuery query, CancellationToken ct = default)
    {
        var (items, total) = await reports.QueryAsync(query, ct);
        return new PagedResult<ReportDto>(
            items.Select(ToDto).ToList(),
            total,
            Math.Max(1, query.Page),
            Math.Clamp(query.PageSize, 1, 100));
    }

    public async Task<ReportDto?> GetReportAsync(Guid id, CancellationToken ct = default)
    {
        var report = await reports.GetByIdAsync(id, ct);
        return report is null ? null : ToDto(report);
    }

    public async Task<UploadReportResponse> UploadAsync(
        IFormFile file,
        string? company,
        int? year,
        string? reportType,
        string? title,
        CancellationToken ct = default)
    {
        if (file.Length == 0)
        {
            throw new DomainException("The uploaded file is empty.");
        }

        if (file.Length > MaxUploadBytes)
        {
            throw new DomainException(
                $"The file exceeds the {MaxUploadBytes / (1024 * 1024)} MB upload limit.", 413);
        }

        var fileName = Path.GetFileName(file.FileName);
        var extension = Path.GetExtension(fileName).ToLowerInvariant();
        if (!AllowedExtensions.Contains(extension))
        {
            throw new DomainException(
                $"Unsupported file type '{extension}'. Supported: {string.Join(", ", AllowedExtensions)}.",
                415);
        }

        // The AI service reads documents from a shared folder, so write there.
        var uploadRoot = Path.Combine(environment.ContentRootPath, "uploads");
        Directory.CreateDirectory(uploadRoot);

        // Prefix with a short unique id so two uploads of the same name coexist.
        var storedName = $"{Guid.NewGuid():N}_{fileName}";
        var destination = Path.Combine(uploadRoot, storedName);

        await using (var stream = File.Create(destination))
        {
            await file.CopyToAsync(stream, ct);
        }

        logger.LogInformation("Stored upload {FileName} ({Bytes} bytes).", fileName, file.Length);

        var companyName = string.IsNullOrWhiteSpace(company) ? "Unknown" : company.Trim();
        var resolvedType = string.IsNullOrWhiteSpace(reportType) ? "Report" : reportType.Trim();
        var resolvedTitle = string.IsNullOrWhiteSpace(title)
            ? Path.GetFileNameWithoutExtension(fileName)
            : title.Trim();

        AiIngestResult indexing;
        try
        {
            indexing = await aiService.IngestAsync(
                new AiIngestRequest(
                    Path: destination,
                    Company: companyName,
                    Year: year,
                    ReportType: resolvedType,
                    Title: resolvedTitle),
                ct);
        }
        catch (AiServiceException)
        {
            // Keep the file: the operator can retry indexing once the AI
            // service is back rather than having to upload it again.
            logger.LogWarning("Indexing failed for {FileName}; file retained.", fileName);
            throw;
        }

        var companyEntity = await companies.GetOrCreateAsync(companyName, ct: ct);
        var report = await reports.AddAsync(
            new FinancialReport
            {
                CompanyId = companyEntity.Id,
                Title = resolvedTitle,
                Year = year ?? indexing.Year,
                ReportType = resolvedType,
                FileName = fileName,
                DocumentId = indexing.DocumentId,
                IndexStatus = MapStatus(indexing.Status),
                IndexMessage = indexing.Message,
                PageCount = indexing.PageCount,
                ChunkCount = indexing.ChunkCount,
                FileSizeBytes = file.Length
            },
            ct);

        report.Company = companyEntity;
        return new UploadReportResponse(ToDto(report), indexing);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct = default)
    {
        var report = await reports.GetByIdAsync(id, ct)
                     ?? throw new DomainException("Report not found.", 404);

        if (!string.IsNullOrWhiteSpace(report.DocumentId))
        {
            try
            {
                await aiService.DeleteDocumentAsync(report.DocumentId, ct);
            }
            catch (AiServiceException exception)
            {
                // Removing the metadata while chunks linger would leave the
                // index unexplainable, so fail loudly instead.
                logger.LogError(exception, "Could not remove {DocumentId} from the index.", report.DocumentId);
                throw;
            }
        }

        await reports.DeleteAsync(report, ct);
        logger.LogInformation("Deleted report {ReportId}.", id);
    }

    public async Task<int> SyncFromIndexAsync(CancellationToken ct = default)
    {
        var documents = await aiService.ListDocumentsAsync(ct);
        var imported = 0;

        foreach (var document in documents)
        {
            if (await reports.GetByDocumentIdAsync(document.DocumentId, ct) is not null)
            {
                continue;
            }

            var companyName = string.IsNullOrWhiteSpace(document.Company)
                ? "Unknown"
                : document.Company;
            var company = await companies.GetOrCreateAsync(
                companyName, TickerFromFileName(document.SourceFile), ct);

            await reports.AddAsync(
                new FinancialReport
                {
                    CompanyId = company.Id,
                    Title = document.Title ?? document.SourceFile ?? document.DocumentId,
                    Year = document.Year,
                    ReportType = document.ReportType ?? "10-K",
                    FileName = document.SourceFile ?? string.Empty,
                    DocumentId = document.DocumentId,
                    IndexStatus = IndexStatus.Indexed,
                    PageCount = document.PageCount,
                    ChunkCount = document.ChunkCount
                },
                ct);

            imported++;
        }

        if (imported > 0)
        {
            logger.LogInformation("Imported {Count} report(s) from the vector index.", imported);
        }

        return imported;
    }

    // ----------------------------------------------------------------- //
    // Mapping
    // ----------------------------------------------------------------- //

    private static ReportDto ToDto(FinancialReport report) =>
        new(
            report.Id,
            report.Title,
            report.Company?.Name ?? "Unknown",
            report.Company?.Ticker,
            report.Year,
            report.ReportType,
            report.FileName,
            report.DocumentId,
            report.IndexStatus.ToString(),
            report.PageCount,
            report.ChunkCount,
            report.FileSizeBytes,
            report.UploadedAt);

    private static IndexStatus MapStatus(string status) => status switch
    {
        "indexed" => IndexStatus.Indexed,
        "skipped_duplicate" => IndexStatus.Duplicate,
        "failed" => IndexStatus.Failed,
        _ => IndexStatus.Pending
    };

    /// <summary>Recover the ticker from the `TICKER_Company_TYPE_YEAR` convention.</summary>
    private static string? TickerFromFileName(string? fileName)
    {
        if (string.IsNullOrWhiteSpace(fileName))
        {
            return null;
        }

        var parts = Path.GetFileNameWithoutExtension(fileName).Split('_');
        return parts.Length == 4 && parts[0].Length <= 6 ? parts[0] : null;
    }
}
