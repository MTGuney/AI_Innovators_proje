using FinRag.Api.Data;
using FinRag.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinRag.Api.Repositories;

public interface ICompanyRepository
{
    Task<Company?> GetByNameAsync(string name, CancellationToken ct = default);

    /// <summary>Fetch the company, creating it if this is the first report for it.</summary>
    Task<Company> GetOrCreateAsync(string name, string? ticker = null, CancellationToken ct = default);

    Task<List<Company>> GetAllAsync(CancellationToken ct = default);

    Task<int> CountAsync(CancellationToken ct = default);

    Task<List<Company>> GetMostQueriedAsync(int limit, CancellationToken ct = default);

    /// <summary>Record that a company was the subject of a question.</summary>
    Task RecordQueryAsync(IEnumerable<string> companyNames, CancellationToken ct = default);
}

public class CompanyRepository(FinRagDbContext db) : ICompanyRepository
{
    public Task<Company?> GetByNameAsync(string name, CancellationToken ct = default) =>
        db.Companies.FirstOrDefaultAsync(company => company.Name == name, ct);

    public async Task<Company> GetOrCreateAsync(
        string name, string? ticker = null, CancellationToken ct = default)
    {
        var existing = await GetByNameAsync(name, ct);
        if (existing is not null)
        {
            if (existing.Ticker is null && ticker is not null)
            {
                existing.Ticker = ticker;
                await db.SaveChangesAsync(ct);
            }

            return existing;
        }

        var company = new Company { Name = name, Ticker = ticker };
        db.Companies.Add(company);
        await db.SaveChangesAsync(ct);
        return company;
    }

    public Task<List<Company>> GetAllAsync(CancellationToken ct = default) =>
        db.Companies.OrderBy(company => company.Name).ToListAsync(ct);

    public Task<int> CountAsync(CancellationToken ct = default) =>
        db.Companies.CountAsync(ct);

    public Task<List<Company>> GetMostQueriedAsync(int limit, CancellationToken ct = default) =>
        db.Companies
            .Where(company => company.QueryCount > 0)
            .OrderByDescending(company => company.QueryCount)
            .ThenByDescending(company => company.LastQueriedAt)
            .Take(limit)
            .ToListAsync(ct);

    public async Task RecordQueryAsync(
        IEnumerable<string> companyNames, CancellationToken ct = default)
    {
        var names = companyNames
            .Where(name => !string.IsNullOrWhiteSpace(name))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        if (names.Count == 0)
        {
            return;
        }

        var companies = await db.Companies
            .Where(company => names.Contains(company.Name))
            .ToListAsync(ct);

        foreach (var company in companies)
        {
            company.QueryCount++;
            company.LastQueriedAt = DateTime.UtcNow;
        }

        await db.SaveChangesAsync(ct);
    }
}
