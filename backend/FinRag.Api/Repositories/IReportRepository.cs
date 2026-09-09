using FinRag.Api.Data;
using FinRag.Api.DTOs;
using FinRag.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinRag.Api.Repositories;

public interface IReportRepository
{
    Task<(List<FinancialReport> Items, int Total)> QueryAsync(
        ReportQuery query, CancellationToken ct = default);

    Task<FinancialReport?> GetByIdAsync(Guid id, CancellationToken ct = default);

    Task<FinancialReport?> GetByDocumentIdAsync(string documentId, CancellationToken ct = default);

    Task<List<FinancialReport>> GetRecentAsync(int limit, CancellationToken ct = default);

    Task<FinancialReport> AddAsync(FinancialReport report, CancellationToken ct = default);

    Task UpdateAsync(FinancialReport report, CancellationToken ct = default);

    Task DeleteAsync(FinancialReport report, CancellationToken ct = default);

    Task<int> CountAsync(CancellationToken ct = default);

    Task<Dictionary<string, int>> CountByYearAsync(CancellationToken ct = default);

    Task<List<string>> GetReportTypesAsync(CancellationToken ct = default);
}

public class ReportRepository(FinRagDbContext db) : IReportRepository
{
    public async Task<(List<FinancialReport> Items, int Total)> QueryAsync(
        ReportQuery query, CancellationToken ct = default)
    {
        var reports = db.Reports.Include(report => report.Company).AsQueryable();

        if (!string.IsNullOrWhiteSpace(query.Search))
        {
            // Case-insensitive contains across the fields a user would search by.
            var term = $"%{query.Search.Trim()}%";
            reports = reports.Where(report =>
                EF.Functions.ILike(report.Title, term) ||
                EF.Functions.ILike(report.FileName, term) ||
                EF.Functions.ILike(report.Company!.Name, term));
        }

        if (!string.IsNullOrWhiteSpace(query.Company))
        {
            reports = reports.Where(report => report.Company!.Name == query.Company);
        }

        if (query.Year is not null)
        {
            reports = reports.Where(report => report.Year == query.Year);
        }

        if (!string.IsNullOrWhiteSpace(query.ReportType))
        {
            reports = reports.Where(report => report.ReportType == query.ReportType);
        }

        var total = await reports.CountAsync(ct);

        var page = Math.Max(1, query.Page);
        var pageSize = Math.Clamp(query.PageSize, 1, 100);

        var items = await reports
            .OrderByDescending(report => report.UploadedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        return (items, total);
    }

    public Task<FinancialReport?> GetByIdAsync(Guid id, CancellationToken ct = default) =>
        db.Reports.Include(report => report.Company)
            .FirstOrDefaultAsync(report => report.Id == id, ct);

    public Task<FinancialReport?> GetByDocumentIdAsync(
        string documentId, CancellationToken ct = default) =>
        db.Reports.Include(report => report.Company)
            .FirstOrDefaultAsync(report => report.DocumentId == documentId, ct);

    public Task<List<FinancialReport>> GetRecentAsync(int limit, CancellationToken ct = default) =>
        db.Reports.Include(report => report.Company)
            .OrderByDescending(report => report.UploadedAt)
            .Take(limit)
            .ToListAsync(ct);

    public async Task<FinancialReport> AddAsync(
        FinancialReport report, CancellationToken ct = default)
    {
        db.Reports.Add(report);
        await db.SaveChangesAsync(ct);
        return report;
    }

    public async Task UpdateAsync(FinancialReport report, CancellationToken ct = default)
    {
        db.Reports.Update(report);
        await db.SaveChangesAsync(ct);
    }

    public async Task DeleteAsync(FinancialReport report, CancellationToken ct = default)
    {
        db.Reports.Remove(report);
        await db.SaveChangesAsync(ct);
    }

    public Task<int> CountAsync(CancellationToken ct = default) => db.Reports.CountAsync(ct);

    public async Task<Dictionary<string, int>> CountByYearAsync(CancellationToken ct = default)
    {
        var grouped = await db.Reports
            .Where(report => report.Year != null)
            .GroupBy(report => report.Year!.Value)
            .Select(group => new { Year = group.Key, Count = group.Count() })
            .OrderBy(entry => entry.Year)
            .ToListAsync(ct);

        return grouped.ToDictionary(
            entry => entry.Year.ToString(), entry => entry.Count);
    }

    public Task<List<string>> GetReportTypesAsync(CancellationToken ct = default) =>
        db.Reports.Select(report => report.ReportType).Distinct().OrderBy(type => type).ToListAsync(ct);
}
