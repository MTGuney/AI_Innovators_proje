using FinRag.Api.DTOs;
using FinRag.Api.Extensions;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace FinRag.Api.Controllers;

[ApiController]
[Route("api/chat")]
[Authorize]
public class ChatController(IChatService chat) : ControllerBase
{
    /// <summary>
    /// Ask a question about the indexed reports. Returns the answer together
    /// with its citations and the chunks retrieval selected.
    /// </summary>
    [HttpPost]
    [ProducesResponseType(typeof(ChatResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<ChatResponse>> Ask(
        [FromBody] ChatRequest request, CancellationToken ct) =>
        Ok(await chat.AskAsync(User.GetUserId(), request, ct));
}
