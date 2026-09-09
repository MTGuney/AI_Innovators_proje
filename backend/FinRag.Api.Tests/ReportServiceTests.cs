using FinRag.Api.Data;
using FinRag.Api.DTOs;
using FinRag.Api.Entities;
using FinRag.Api.Repositories;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Hosting;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace FinRag.Api.Tests;

/// <summary>
/// Report CRUD and the invariant that matters most: PostgreSQL metadata and the
/// vector index must not drift apart.
/// </summary>
public class ReportServiceTests : IDisposable
{
    private readonly FinRagDbContext _db;
    private readonly Mock<IAiServiceClient> _ai = new();
    private readonly string _contentRoot = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));

    public ReportServiceTests()
    {
        var options = new DbContextOptionsBuilder<FinRagDbContext>()
            .UseInMemoryDatabase($"reports-{Guid.NewGuid()}")
            .Options;
        _db = new FinRagDbContext(options);
        Directory.CreateDirectory(_contentRoot);
    }

    public void Dispose()
    {
        _db.Dispose();
        if (Directory.Exists(_contentRoot))
        {
            Directory.Delete(_contentRoot, recursive: true);
        }
    }

    private ReportService BuildService()
    {
        var environment = new Mock<IWebHostEnvironment>();
        environment.SetupGet(env => env.ContentRootPath).Returns(_contentRoot);

        return new ReportService(
            new ReportRepository(_db),
            new CompanyRepository(_db),
            _ai.Object,
            environment.Object,
            NullLogger<ReportService>.Instance);
    }

    private async Task<FinancialReport> SeedReportAsync(
        string company = "Apple Inc", int year = 2024, string title = "Apple 10-K 2024")
    {
        var companyEntity = await new CompanyRepository(_db).GetOrCreateAsync(company);
        var report = new FinancialReport
        {
            CompanyId = companyEntity.Id,
            Title = title,
            Year = year,
            ReportType = "10-K",
            FileName = $"{company}_{year}.txt",
            DocumentId = $"{company.ToLowerInvariant().Replace(' ', '-')}-{year}",
            IndexStatus = IndexStatus.Indexed,
            ChunkCount = 120
        };
        _db.Reports.Add(report);
        await _db.SaveChangesAsync();
        return report;
    }

    [Fact]
    public async Task GetReportsAsync_FiltersByCompanyAndYear()
    {
        await SeedReportAsync("Apple Inc", 2024);
        await SeedReportAsync("Apple Inc", 2023);
        await SeedReportAsync("Microsoft Corp", 2024);

        var byCompany = await BuildService().GetReportsAsync(new ReportQuery(Company: "Apple Inc"));
        Assert.Equal(2, byCompany.Total);

        var byYear = await BuildService().GetReportsAsync(new ReportQuery(Year: 2024));
        Assert.Equal(2, byYear.Total);

        var both = await BuildService()
            .GetReportsAsync(new ReportQuery(Company: "Apple Inc", Year: 2023));
        Assert.Equal(1, both.Total);
    }

    [Fact]
    public async Task GetReportsAsync_PagesResults()
    {
        for (var index = 0; index < 5; index++)
        {
            await SeedReportAsync("Apple Inc", 2020 + index, $"Report {index}");
        }

        var page = await BuildService().GetReportsAsync(new ReportQuery(Page: 2, PageSize: 2));

        Assert.Equal(5, page.Total);
        Assert.Equal(2, page.Items.Count);
        Assert.Equal(2, page.Page);
    }

    [Fact]
    public async Task DeleteAsync_RemovesTheDocumentFromTheIndexToo()
    {
        var report = await SeedReportAsync();
        _ai.Setup(client => client.DeleteDocumentAsync(report.DocumentId!, It.IsAny<CancellationToken>()))
           .ReturnsAsync(true);

        await BuildService().DeleteAsync(report.Id);

        _ai.Verify(
            client => client.DeleteDocumentAsync(report.DocumentId!, It.IsAny<CancellationToken>()),
            Times.Once);
        Assert.Empty(_db.Reports);
    }

    [Fact]
    public async Task DeleteAsync_KeepsMetadataWhenTheIndexCannotBeUpdated()
    {
        var report = await SeedReportAsync();
        _ai.Setup(client => client.DeleteDocumentAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
           .ThrowsAsync(new AiServiceException("unavailable"));

        await Assert.ThrowsAsync<AiServiceException>(() => BuildService().DeleteAsync(report.Id));

        // Deleting metadata while chunks survive would leave answers citing a
        // report the catalogue no longer knows about.
        Assert.Single(_db.Reports);
    }

    [Fact]
    public async Task DeleteAsync_ThrowsNotFoundForUnknownId()
    {
        var error = await Assert.ThrowsAsync<DomainException>(
            () => BuildService().DeleteAsync(Guid.NewGuid()));

        Assert.Equal(404, error.StatusCode);
    }

    [Fact]
    public async Task SyncFromIndexAsync_ImportsDocumentsIndexedOutsideTheApi()
    {
        _ai.Setup(client => client.ListDocumentsAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync(
           [
               new IndexedDocument(
                   "apple-inc-2024-10-k", "AAPL_Apple-Inc_10-K_2024.txt",
                   "Apple Annual Report", "Apple Inc", 2024, "10-K", 121, 40)
           ]);

        var imported = await BuildService().SyncFromIndexAsync();

        Assert.Equal(1, imported);
        var report = await _db.Reports.Include(r => r.Company).SingleAsync();
        Assert.Equal("Apple Inc", report.Company!.Name);
        // The ticker is recovered from the dataset's filename convention.
        Assert.Equal("AAPL", report.Company.Ticker);
        Assert.Equal(2024, report.Year);
        Assert.Equal(IndexStatus.Indexed, report.IndexStatus);
    }

    [Fact]
    public async Task SyncFromIndexAsync_IsIdempotent()
    {
        _ai.Setup(client => client.ListDocumentsAsync(It.IsAny<CancellationToken>()))
           .ReturnsAsync(
           [
               new IndexedDocument(
                   "apple-inc-2024-10-k", "AAPL_Apple-Inc_10-K_2024.txt",
                   "Apple Annual Report", "Apple Inc", 2024, "10-K", 121, 40)
           ]);

        var service = BuildService();
        Assert.Equal(1, await service.SyncFromIndexAsync());
        Assert.Equal(0, await service.SyncFromIndexAsync());
        Assert.Single(_db.Reports);
    }
}
