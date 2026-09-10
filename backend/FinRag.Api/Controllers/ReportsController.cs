using FinRag.Api.DTOs;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace FinRag.Api.Controllers;

[ApiController]
[Route("api/reports")]
public class ReportsController(IReportService reports) : ControllerBase
{
    /// <summary>Browse the report catalogue with search, filters and paging.</summary>
    [HttpGet]
    [ProducesResponseType(typeof(PagedResult<ReportDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<PagedResult<ReportDto>>> GetReports(
        [FromQuery] ReportQuery query, CancellationToken ct) =>
        Ok(await reports.GetReportsAsync(query, ct));

    /// <summary>Metadata for a single report.</summary>
    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(ReportDto), StatusCodes.Status200OK)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ReportDto>> GetReport(Guid id, CancellationToken ct)
    {
        var report = await reports.GetReportAsync(id, ct);
        return report is null
            ? NotFound(new ApiError("Report not found."))
            : Ok(report);
    }

    /// <summary>Upload a report and index it for retrieval.</summary>
    [HttpPost("upload")]
    [RequestSizeLimit(64 * 1024 * 1024)]
    [ProducesResponseType(typeof(UploadReportResponse), StatusCodes.Status201Created)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status415UnsupportedMediaType)]
    public async Task<ActionResult<UploadReportResponse>> Upload(
        IFormFile file,
        [FromForm] string? company,
        [FromForm] int? year,
        [FromForm] string? reportType,
        [FromForm] string? title,
        CancellationToken ct)
    {
        var result = await reports.UploadAsync(file, company, year, reportType, title, ct);
        return CreatedAtAction(nameof(GetReport), new { id = result.Report.Id }, result);
    }

    /// <summary>Delete a report and remove its chunks from the index.</summary>
    [HttpDelete("{id:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status404NotFound)]
    public async Task<IActionResult> Delete(Guid id, CancellationToken ct)
    {
        await reports.DeleteAsync(id, ct);
        return NoContent();
    }

    /// <summary>Import documents indexed directly by the AI service's CLI.</summary>
    [HttpPost("sync")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    public async Task<IActionResult> Sync(CancellationToken ct) =>
        Ok(new { imported = await reports.SyncFromIndexAsync(ct) });
}
