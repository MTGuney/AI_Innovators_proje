using FinRag.Api.DTOs;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace FinRag.Api.Controllers;

[ApiController]
[Route("api/compare")]
[Authorize]
public class CompareController(IAiServiceClient aiService) : ControllerBase
{
    /// <summary>
    /// Compare companies on a metric. The response keeps retrieved facts
    /// separate from the model's summary so the UI can label each.
    /// </summary>
    [HttpPost]
    [ProducesResponseType(typeof(ComparisonResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<ComparisonResponse>> Compare(
        [FromBody] ComparisonRequest request, CancellationToken ct)
    {
        if (request.Companies is null || request.Companies.Count < 2)
        {
            return BadRequest(new ApiError("Select at least two companies to compare."));
        }

        if (string.IsNullOrWhiteSpace(request.Metric))
        {
            return BadRequest(new ApiError("A metric is required."));
        }

        return Ok(await aiService.CompareAsync(request, ct));
    }

    /// <summary>Companies available in the index, for the comparison selector.</summary>
    [HttpGet("companies")]
    [ProducesResponseType(typeof(List<string>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<string>>> Companies(CancellationToken ct)
    {
        var documents = await aiService.ListDocumentsAsync(ct);
        return Ok(documents
            .Where(document => !string.IsNullOrWhiteSpace(document.Company))
            .Select(document => document.Company!)
            .Distinct()
            .OrderBy(name => name)
            .ToList());
    }
}
