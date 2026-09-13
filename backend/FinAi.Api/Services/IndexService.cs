using FinAi.Api.DTOs;

namespace FinAi.Api.Services;

public interface IIndexService
{
    Task<IndexStatusDto> GetStatusAsync(CancellationToken ct = default);
}

/// <summary>
/// Reports the state of the retrieval index and the service behind it.
/// The counts come from the AI service rather than our own tables, because
/// the index is its business and ours can drift after a manual re-index.
/// </summary>
public class IndexService(IAiServiceClient aiService) : IIndexService
{
    public async Task<IndexStatusDto> GetStatusAsync(CancellationToken ct = default)
    {
        var health = await aiService.GetHealthAsync(ct);

        if (health is null)
        {
            return new IndexStatusDto(false, "The AI service is unreachable.", 0, 0);
        }

        var documents = 0;
        var chunks = 0;

        try
        {
            var stats = await aiService.GetIndexStatsAsync(ct);
            documents = stats.TotalDocuments;
            chunks = stats.TotalChunks;
        }
        catch (AiServiceException)
        {
            // Health still renders; the counts simply stay at zero.
        }

        return new IndexStatusDto(
            AiServiceHealthy: health.Status == "ok",
            AiServiceDetail: string.Join(
                "; ", health.Components.Select(c => $"{c.Name}: {c.Detail}")),
            IndexedDocuments: documents,
            IndexedChunks: chunks);
    }
}
