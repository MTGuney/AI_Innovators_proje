using FinAi.Api.Data;
using FinAi.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinAi.Api.Repositories;

public interface IConversationRepository
{
    Task<List<Conversation>> GetForUserAsync(Guid userId, CancellationToken ct = default);

    /// <summary>Load a conversation with its messages, scoped to its owner.</summary>
    Task<Conversation?> GetWithMessagesAsync(
        Guid conversationId, Guid userId, CancellationToken ct = default);

    Task<Conversation> CreateAsync(Conversation conversation, CancellationToken ct = default);

    Task AddMessagesAsync(
        Conversation conversation, IEnumerable<Message> messages, CancellationToken ct = default);

    Task DeleteAsync(Conversation conversation, CancellationToken ct = default);
}

public class ConversationRepository(FinAiDbContext db) : IConversationRepository
{
    public Task<List<Conversation>> GetForUserAsync(Guid userId, CancellationToken ct = default) =>
        db.Conversations
            .Where(conversation => conversation.UserId == userId)
            .Include(conversation => conversation.Messages)
            .OrderByDescending(conversation => conversation.UpdatedAt)
            .ToListAsync(ct);

    public Task<Conversation?> GetWithMessagesAsync(
        Guid conversationId, Guid userId, CancellationToken ct = default) =>
        db.Conversations
            .Include(conversation => conversation.Messages.OrderBy(message => message.CreatedAt))
            .FirstOrDefaultAsync(
                conversation => conversation.Id == conversationId && conversation.UserId == userId,
                ct);

    public async Task<Conversation> CreateAsync(
        Conversation conversation, CancellationToken ct = default)
    {
        db.Conversations.Add(conversation);
        await db.SaveChangesAsync(ct);
        return conversation;
    }

    public async Task AddMessagesAsync(
        Conversation conversation, IEnumerable<Message> messages, CancellationToken ct = default)
    {
        db.Messages.AddRange(messages);
        conversation.UpdatedAt = DateTime.UtcNow;
        db.Conversations.Update(conversation);
        await db.SaveChangesAsync(ct);
    }

    public async Task DeleteAsync(Conversation conversation, CancellationToken ct = default)
    {
        db.Conversations.Remove(conversation);
        await db.SaveChangesAsync(ct);
    }
}
