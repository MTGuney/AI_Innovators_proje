using FinAi.Api.DTOs;
using FinAi.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace FinAi.Api.Controllers;

[ApiController]
[Route("api/index")]
public class IndexController(IIndexService index) : ControllerBase
{
    /// <summary>Health of the AI service and the size of the retrieval index.</summary>
    [HttpGet("status")]
    [ProducesResponseType(typeof(IndexStatusDto), StatusCodes.Status200OK)]
    public async Task<ActionResult<IndexStatusDto>> Status(CancellationToken ct) =>
        Ok(await index.GetStatusAsync(ct));
}
