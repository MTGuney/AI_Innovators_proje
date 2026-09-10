using FinRag.Api.DTOs;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace FinRag.Api.Controllers;

[ApiController]
[Route("api/conversations")]
public class ConversationsController(IChatService chat, LocalUser user) : ControllerBase
{
    /// <summary>Recorded conversations, most recent first.</summary>
    [HttpGet]
    [ProducesResponseType(typeof(List<ConversationSummaryDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<List<ConversationSummaryDto>>> GetConversations(
        CancellationToken ct) =>
        Ok(await chat.GetConversationsAsync(user.Id, ct));

    /// <summary>A conversation with its full message history and citations.</summary>
    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(ConversationDetailDto), StatusCodes.Status200OK)]
    [ProducesResponseType(typeof(ApiError), StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ConversationDetailDto>> GetConversation(
        Guid id, CancellationToken ct)
    {
        var conversation = await chat.GetConversationAsync(user.Id, id, ct);
        return conversation is null
            ? NotFound(new ApiError("Conversation not found."))
            : Ok(conversation);
    }

    [HttpDelete("{id:guid}")]
    [ProducesResponseType(StatusCodes.Status204NoContent)]
    public async Task<IActionResult> Delete(Guid id, CancellationToken ct)
    {
        await chat.DeleteConversationAsync(user.Id, id, ct);
        return NoContent();
    }
}
