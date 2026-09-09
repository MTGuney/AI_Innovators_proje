using FinRag.Api.DTOs;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace FinRag.Api.Controllers;

[ApiController]
[Route("api/search")]
[Authorize]
public class SearchController(IAiServiceClient aiService) : ControllerBase
{
    /// <summary>
    /// Semantic search with no generation. This is the transparency endpoint:
    /// it shows exactly which passages retrieval would feed to the model.
    /// </summary>
    [HttpGet]
    [ProducesResponseType(typeof(SearchResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<SearchResponse>> Search(
        [FromQuery] string q,
        [FromQuery] int? topK,
        [FromQuery] string? company,
        [FromQuery] int? year,
        [FromQuery] string? reportType,
        CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(q) || q.Trim().Length < 3)
        {
            return BadRequest(new ApiError("A search query of at least 3 characters is required."));
        }

        var filters = new RetrievalFilters(
            Companies: company is null ? null : [company],
            Years: year is null ? null : [year.Value],
            ReportTypes: reportType is null ? null : [reportType]);

        return Ok(await aiService.SearchAsync(new SearchRequest(q.Trim(), topK, null, filters), ct));
    }
}
