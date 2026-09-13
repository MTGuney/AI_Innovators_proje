using FinAi.Api.Data;
using FinAi.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinAi.Api.Repositories;

public interface ICompanyRepository
{
    Task<Company?> GetByNameAsync(string name, CancellationToken ct = default);

    /// <summary>Fetch the company, creating it if this is the first report for it.</summary>
    Task<Company> GetOrCreateAsync(string name, string? ticker = null, CancellationToken ct = default);

    Task<List<Company>> GetAllAsync(CancellationToken ct = default);
}

public class CompanyRepository(FinAiDbContext db) : ICompanyRepository
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
}
