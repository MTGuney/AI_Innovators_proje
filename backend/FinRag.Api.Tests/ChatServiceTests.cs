using FinRag.Api.Data;
using FinRag.Api.DTOs;
using FinRag.Api.Entities;
using FinRag.Api.Repositories;
using FinRag.Api.Services;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace FinRag.Api.Tests;

/// <summary>
/// Covers the chat orchestration: history is forwarded, answers and their
/// citations are persisted, and company usage is recorded from real citations.
/// </summary>
public class ChatServiceTests : IDisposable
{
    private readonly FinRagDbContext _db;
    private readonly Guid _userId = Guid.NewGuid();

    public ChatServiceTests()
    {
        var options = new DbContextOptionsBuilder<FinRagDbContext>()
            .UseInMemoryDatabase($"chat-{Guid.NewGuid()}")
            .Options;

        _db = new FinRagDbContext(options);
        _db.Users.Add(new User
        {
            Id = _userId,
            Email = "demo@finrag.local",
            DisplayName = "Demo",
            PasswordHash = "x"
        });
        _db.Companies.Add(new Company { Name = "Apple Inc" });
        _db.SaveChanges();
    }

    public void Dispose() => _db.Dispose();

    private static RagAnswer BuildAnswer(string answer = "Revenue grew 12.4% [S1].") =>
        new(
            Answer: answer,
            KeyPoints: ["Revenue was $4,820m"],
            Sources:
            [
                new SourceCitation(
                    "Apple Annual Report 2024", "apple-2024", 32, 0.91,
                    "Apple Inc", 2024, "10-K", "Item 7. MD&A", "apple::p32::c4",
                    "Total revenue was $4,820 million.")
            ],
            Confidence: "high",
            Grounded: true,
            Model: "test-model",
            ElapsedMs: 1200,
            RetrievedChunks: [],
            UnsupportedFigures: []);

    private ChatService BuildService(Mock<IAiServiceClient> ai) =>
        new(
            new ConversationRepository(_db),
            new CompanyRepository(_db),
            ai.Object,
            NullLogger<ChatService>.Instance);

    [Fact]
    public async Task AskAsync_CreatesConversationAndPersistsBothMessages()
    {
        var ai = new Mock<IAiServiceClient>();
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .ReturnsAsync(BuildAnswer());

        var response = await BuildService(ai).AskAsync(
            _userId, new ChatRequest("Did revenue increase?"));

        var messages = await _db.Messages
            .Where(message => message.ConversationId == response.ConversationId)
            .OrderBy(message => message.CreatedAt)
            .ToListAsync();

        Assert.Equal(2, messages.Count);
        Assert.Equal(MessageRole.User, messages[0].Role);
        Assert.Equal("Did revenue increase?", messages[0].Content);
        Assert.Equal(MessageRole.Assistant, messages[1].Role);
        Assert.Contains("12.4%", messages[1].Content);
        // Citations are stored verbatim so old answers stay verifiable.
        Assert.Contains("apple::p32::c4", messages[1].SourcesJson);
    }

    [Fact]
    public async Task AskAsync_TitlesTheConversationFromTheFirstQuestion()
    {
        var ai = new Mock<IAiServiceClient>();
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .ReturnsAsync(BuildAnswer());

        var response = await BuildService(ai).AskAsync(
            _userId, new ChatRequest("What are the main risk factors?"));

        var conversation = await _db.Conversations.FindAsync(response.ConversationId);
        Assert.Equal("What are the main risk factors?", conversation!.Title);
    }

    [Fact]
    public async Task AskAsync_SendsPriorTurnsAsHistory()
    {
        var ai = new Mock<IAiServiceClient>();
        RagQueryRequest? captured = null;
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .Callback<RagQueryRequest, CancellationToken>((request, _) => captured = request)
          .ReturnsAsync(BuildAnswer());

        var service = BuildService(ai);
        var first = await service.AskAsync(_userId, new ChatRequest("What was revenue?"));
        await service.AskAsync(
            _userId, new ChatRequest("How does that compare to 2023?", first.ConversationId));

        // Without history the follow-up's pronoun could not be resolved.
        Assert.NotNull(captured!.History);
        Assert.Equal(2, captured.History!.Count);
        Assert.Equal("user", captured.History[0].Role);
        Assert.Equal("What was revenue?", captured.History[0].Content);
    }

    [Fact]
    public async Task AskAsync_ForwardsFilters()
    {
        var ai = new Mock<IAiServiceClient>();
        RagQueryRequest? captured = null;
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .Callback<RagQueryRequest, CancellationToken>((request, _) => captured = request)
          .ReturnsAsync(BuildAnswer());

        await BuildService(ai).AskAsync(
            _userId,
            new ChatRequest("Revenue?", null, Companies: ["Apple Inc"], Years: [2024]));

        Assert.Equal(["Apple Inc"], captured!.Filters!.Companies);
        Assert.Equal([2024], captured.Filters.Years);
    }

    [Fact]
    public async Task AskAsync_CountsQueriesAgainstTheCitedCompany()
    {
        var ai = new Mock<IAiServiceClient>();
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .ReturnsAsync(BuildAnswer());

        await BuildService(ai).AskAsync(_userId, new ChatRequest("Did revenue increase?"));

        var company = await _db.Companies.FirstAsync(c => c.Name == "Apple Inc");
        Assert.Equal(1, company.QueryCount);
        Assert.NotNull(company.LastQueriedAt);
    }

    [Fact]
    public async Task AskAsync_RejectsAConversationOwnedByAnotherUser()
    {
        var ai = new Mock<IAiServiceClient>();
        var foreign = new Conversation { UserId = Guid.NewGuid(), Title = "Not yours" };
        _db.Conversations.Add(foreign);
        await _db.SaveChangesAsync();

        await Assert.ThrowsAsync<DomainException>(() =>
            BuildService(ai).AskAsync(_userId, new ChatRequest("Revenue?", foreign.Id)));
    }

    [Fact]
    public async Task GetConversationAsync_ReturnsNullForAnotherUsersConversation()
    {
        var ai = new Mock<IAiServiceClient>();
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .ReturnsAsync(BuildAnswer());

        var response = await BuildService(ai).AskAsync(_userId, new ChatRequest("Revenue?"));

        var result = await BuildService(ai)
            .GetConversationAsync(Guid.NewGuid(), response.ConversationId);

        Assert.Null(result);
    }

    [Fact]
    public async Task GetConversationAsync_RehydratesStoredCitations()
    {
        var ai = new Mock<IAiServiceClient>();
        ai.Setup(client => client.QueryAsync(It.IsAny<RagQueryRequest>(), It.IsAny<CancellationToken>()))
          .ReturnsAsync(BuildAnswer());

        var service = BuildService(ai);
        var response = await service.AskAsync(_userId, new ChatRequest("Revenue?"));

        var detail = await service.GetConversationAsync(_userId, response.ConversationId);

        var assistant = detail!.Messages.Single(message => message.Role == "assistant");
        Assert.Single(assistant.Sources);
        Assert.Equal(32, assistant.Sources[0].Page);
        Assert.Equal("high", assistant.Confidence);
        Assert.Single(assistant.KeyPoints);
    }
}
