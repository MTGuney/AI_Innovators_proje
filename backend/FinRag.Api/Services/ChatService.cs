using System.Text.Json;
using FinRag.Api.DTOs;
using FinRag.Api.Entities;
using FinRag.Api.Repositories;

namespace FinRag.Api.Services;

public interface IChatService
{
    Task<ChatResponse> AskAsync(Guid userId, ChatRequest request, CancellationToken ct = default);

    Task<List<ConversationSummaryDto>> GetConversationsAsync(
        Guid userId, CancellationToken ct = default);

    Task<ConversationDetailDto?> GetConversationAsync(
        Guid userId, Guid conversationId, CancellationToken ct = default);

    Task DeleteConversationAsync(Guid userId, Guid conversationId, CancellationToken ct = default);
}

/// <summary>
/// Orchestrates a chat turn: load history, ask the RAG service, then persist the
/// question, the answer and the evidence behind it.
/// </summary>
public class ChatService(
    IConversationRepository conversations,
    IAiServiceClient aiService,
    ILogger<ChatService> logger) : IChatService
{
    /// <summary>Turns of history sent to the RAG service for follow-up resolution.</summary>
    private const int HistoryTurns = 6;

    private const int TitleMaxChars = 80;

    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task<ChatResponse> AskAsync(
        Guid userId, ChatRequest request, CancellationToken ct = default)
    {
        var conversation = await ResolveConversationAsync(userId, request, ct);

        var history = conversation.Messages
            .OrderBy(message => message.CreatedAt)
            .TakeLast(HistoryTurns)
            .Select(message => new ChatTurn(
                message.Role == MessageRole.User ? "user" : "assistant", message.Content))
            .ToList();

        var answer = await aiService.QueryAsync(
            new RagQueryRequest(
                Question: request.Question.Trim(),
                TopK: request.TopK,
                Filters: new RetrievalFilters(
                    request.Companies, request.Years, request.ReportTypes, request.DocumentIds),
                History: history),
            ct);

        var askedAt = DateTime.UtcNow;
        var userMessage = new Message
        {
            ConversationId = conversation.Id,
            Role = MessageRole.User,
            Content = request.Question.Trim(),
            CreatedAt = askedAt
        };

        var assistantMessage = new Message
        {
            ConversationId = conversation.Id,
            Role = MessageRole.Assistant,
            Content = answer.Answer,
            SourcesJson = JsonSerializer.Serialize(answer.Sources, Json),
            KeyPointsJson = JsonSerializer.Serialize(answer.KeyPoints, Json),
            UnsupportedFiguresJson = JsonSerializer.Serialize(answer.UnsupportedFigures, Json),
            Confidence = answer.Confidence,
            Grounded = answer.Grounded,
            ElapsedMs = answer.ElapsedMs,
            Model = answer.Model,
            // One millisecond later so ordering by timestamp is deterministic.
            CreatedAt = askedAt.AddMilliseconds(1)
        };

        await conversations.AddMessagesAsync(
            conversation, [userMessage, assistantMessage], ct);

        logger.LogInformation(
            "Answered in conversation {ConversationId} ({ElapsedMs}ms, {SourceCount} sources).",
            conversation.Id, answer.ElapsedMs, answer.Sources.Count);

        return new ChatResponse(
            conversation.Id,
            assistantMessage.Id,
            answer.Answer,
            answer.KeyPoints,
            answer.Sources,
            answer.RetrievedChunks,
            answer.Confidence,
            answer.Grounded,
            answer.UnsupportedFigures,
            answer.Model,
            answer.ElapsedMs,
            assistantMessage.CreatedAt);
    }

    public async Task<List<ConversationSummaryDto>> GetConversationsAsync(
        Guid userId, CancellationToken ct = default)
    {
        var items = await conversations.GetForUserAsync(userId, ct);
        return items
            .Select(conversation => new ConversationSummaryDto(
                conversation.Id,
                conversation.Title,
                conversation.Messages.Count,
                conversation.CreatedAt,
                conversation.UpdatedAt))
            .ToList();
    }

    public async Task<ConversationDetailDto?> GetConversationAsync(
        Guid userId, Guid conversationId, CancellationToken ct = default)
    {
        var conversation = await conversations.GetWithMessagesAsync(conversationId, userId, ct);
        if (conversation is null)
        {
            return null;
        }

        return new ConversationDetailDto(
            conversation.Id,
            conversation.Title,
            conversation.CreatedAt,
            conversation.UpdatedAt,
            conversation.Messages.Select(ToDto).ToList());
    }

    public async Task DeleteConversationAsync(
        Guid userId, Guid conversationId, CancellationToken ct = default)
    {
        var conversation = await conversations.GetWithMessagesAsync(conversationId, userId, ct)
                           ?? throw new DomainException("Conversation not found.", 404);

        await conversations.DeleteAsync(conversation, ct);
    }

    // ----------------------------------------------------------------- //
    // Internals
    // ----------------------------------------------------------------- //

    private async Task<Conversation> ResolveConversationAsync(
        Guid userId, ChatRequest request, CancellationToken ct)
    {
        if (request.ConversationId is null)
        {
            return await conversations.CreateAsync(
                new Conversation { UserId = userId, Title = BuildTitle(request.Question) }, ct);
        }

        return await conversations.GetWithMessagesAsync(request.ConversationId.Value, userId, ct)
               ?? throw new DomainException("Conversation not found.", 404);
    }

    private static string BuildTitle(string question)
    {
        var title = question.Trim();
        return title.Length <= TitleMaxChars ? title : title[..TitleMaxChars].TrimEnd() + "...";
    }

    private static MessageDto ToDto(Message message) =>
        new(
            message.Id,
            message.Role == MessageRole.User ? "user" : "assistant",
            message.Content,
            Deserialize<List<string>>(message.KeyPointsJson) ?? [],
            Deserialize<List<SourceCitation>>(message.SourcesJson) ?? [],
            message.Confidence,
            message.Grounded,
            Deserialize<List<string>>(message.UnsupportedFiguresJson) ?? [],
            message.ElapsedMs,
            message.Model,
            message.CreatedAt);

    private static T? Deserialize<T>(string? json) where T : class
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<T>(json, Json);
        }
        catch (JsonException)
        {
            // A stored payload from an older shape should not break history.
            return null;
        }
    }
}
