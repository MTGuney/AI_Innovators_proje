using FinRag.Api.DTOs;
using FinRag.Api.Entities;
using FinRag.Api.Repositories;

namespace FinRag.Api.Services;

public interface IDashboardService
{
    Task<DashboardStatsDto> GetStatsAsync(CancellationToken ct = default);
}

public class DashboardService(
    IReportRepository reports,
    ICompanyRepository companies,
    IAiServiceClient aiService) : IDashboardService
{
    private const int RecentUploadLimit = 5;

    private const int MostQueriedLimit = 5;

    public async Task<DashboardStatsDto> GetStatsAsync(CancellationToken ct = default)
    {
        var companyCount = await companies.CountAsync(ct);
        var reportCount = await reports.CountAsync(ct);
        var recent = await reports.GetRecentAsync(RecentUploadLimit, ct);
        var mostQueried = await companies.GetMostQueriedAsync(MostQueriedLimit, ct);
        var byYear = await reports.CountByYearAsync(ct);
        var reportTypes = await reports.GetReportTypesAsync(ct);

        // The index is the AI service's business, so ask it rather than
        // trusting our own counters, which can drift after a manual re-index.
        var health = await aiService.GetHealthAsync(ct);
        var indexedDocuments = 0;
        var indexedChunks = 0;

        if (health is not null)
        {
            try
            {
                var stats = await aiService.GetIndexStatsAsync(ct);
                indexedDocuments = stats.TotalDocuments;
                indexedChunks = stats.TotalChunks;
            }
            catch (AiServiceException)
            {
                // The dashboard still renders with the database-derived numbers.
            }
        }

        return new DashboardStatsDto(
            TotalCompanies: companyCount,
            TotalReports: reportCount,
            IndexedDocuments: indexedDocuments,
            IndexedChunks: indexedChunks,
            RecentUploads: recent.Select(ToDto).ToList(),
            MostQueriedCompanies: mostQueried
                .Select(company => new CompanyUsageDto(
                    company.Name, company.QueryCount, company.LastQueriedAt))
                .ToList(),
            ReportsByYear: byYear,
            ReportTypes: reportTypes,
            AiServiceHealthy: health?.Status == "ok",
            AiServiceDetail: health is null
                ? "The AI service is unreachable."
                : string.Join("; ", health.Components.Select(c => $"{c.Name}: {c.Detail}")));
    }

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
}
