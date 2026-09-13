using System.Net.Http.Json;
using System.Text.Json;
using FinAi.Api.DTOs;

namespace FinAi.Api.Services;

/// <summary>Raised when the AI service is unreachable or returns an error.</summary>
public class AiServiceException(string message, int statusCode = 503, string? detail = null)
    : Exception(message)
{
    public int StatusCode { get; } = statusCode;

    public string? Detail { get; } = detail;
}

public interface IAiServiceClient
{
    Task<RagAnswer> QueryAsync(RagQueryRequest request, CancellationToken ct = default);

    Task<SearchResponse> SearchAsync(SearchRequest request, CancellationToken ct = default);

    Task<ComparisonResponse> CompareAsync(ComparisonRequest request, CancellationToken ct = default);

    Task<AiIngestResult> IngestAsync(AiIngestRequest request, CancellationToken ct = default);

    Task<bool> DeleteDocumentAsync(string documentId, CancellationToken ct = default);

    Task<IndexStats> GetIndexStatsAsync(CancellationToken ct = default);

    Task<List<IndexedDocument>> ListDocumentsAsync(CancellationToken ct = default);

    Task<AiHealthResponse?> GetHealthAsync(CancellationToken ct = default);
}

/// <summary>
/// The single place the backend talks to the Python RAG service. Controllers
/// and services depend on this interface, never on HttpClient directly.
/// </summary>
public class AiServiceClient(HttpClient httpClient, ILogger<AiServiceClient> logger) : IAiServiceClient
{
    /// <summary>The Python service speaks snake_case; translate at the boundary.</summary>
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull
    };

    public Task<RagAnswer> QueryAsync(RagQueryRequest request, CancellationToken ct = default) =>
        PostAsync<RagQueryRequest, RagAnswer>("/query", request, ct);

    public Task<SearchResponse> SearchAsync(SearchRequest request, CancellationToken ct = default) =>
        PostAsync<SearchRequest, SearchResponse>("/search", request, ct);

    public Task<ComparisonResponse> CompareAsync(ComparisonRequest request, CancellationToken ct = default) =>
        PostAsync<ComparisonRequest, ComparisonResponse>("/compare", request, ct);

    public Task<AiIngestResult> IngestAsync(AiIngestRequest request, CancellationToken ct = default) =>
        PostAsync<AiIngestRequest, AiIngestResult>("/documents/ingest", request, ct);

    public async Task<bool> DeleteDocumentAsync(string documentId, CancellationToken ct = default)
    {
        try
        {
            var response = await httpClient.DeleteAsync($"/documents/{Uri.EscapeDataString(documentId)}", ct);

            // Already absent is a success for the caller's purposes.
            if (response.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                return false;
            }

            await EnsureSuccessAsync(response, ct);
            return true;
        }
        catch (HttpRequestException exception)
        {
            throw Unreachable(exception);
        }
    }

    public Task<IndexStats> GetIndexStatsAsync(CancellationToken ct = default) =>
        GetAsync<IndexStats>("/documents/stats", ct);

    public Task<List<IndexedDocument>> ListDocumentsAsync(CancellationToken ct = default) =>
        GetAsync<List<IndexedDocument>>("/documents", ct);

    /// <summary>Health probe: returns null instead of throwing, for dashboards.</summary>
    public async Task<AiHealthResponse?> GetHealthAsync(CancellationToken ct = default)
    {
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(10));

            var response = await httpClient.GetAsync("/health", timeout.Token);
            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            return await response.Content.ReadFromJsonAsync<AiHealthResponse>(JsonOptions, ct);
        }
        catch (Exception exception)
        {
            logger.LogWarning(exception, "AI service health probe failed.");
            return null;
        }
    }

    // ----------------------------------------------------------------- //
    // Internals
    // ----------------------------------------------------------------- //

    private async Task<TResponse> PostAsync<TRequest, TResponse>(
        string path, TRequest payload, CancellationToken ct)
    {
        try
        {
            var response = await httpClient.PostAsJsonAsync(path, payload, JsonOptions, ct);
            await EnsureSuccessAsync(response, ct);

            return await response.Content.ReadFromJsonAsync<TResponse>(JsonOptions, ct)
                   ?? throw new AiServiceException("The AI service returned an empty response.");
        }
        catch (HttpRequestException exception)
        {
            throw Unreachable(exception);
        }
        catch (TaskCanceledException exception) when (!ct.IsCancellationRequested)
        {
            logger.LogError(exception, "AI service timed out calling {Path}.", path);
            throw new AiServiceException(
                "The AI service took too long to respond. The local model may still be loading.",
                504);
        }
    }

    private async Task<TResponse> GetAsync<TResponse>(string path, CancellationToken ct)
    {
        try
        {
            var response = await httpClient.GetAsync(path, ct);
            await EnsureSuccessAsync(response, ct);

            return await response.Content.ReadFromJsonAsync<TResponse>(JsonOptions, ct)
                   ?? throw new AiServiceException("The AI service returned an empty response.");
        }
        catch (HttpRequestException exception)
        {
            throw Unreachable(exception);
        }
    }

    /// <summary>Surface the AI service's own message rather than a bare status code.</summary>
    private async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken ct)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        string? error = null;
        string? detail = null;
        try
        {
            var body = await response.Content.ReadFromJsonAsync<AiErrorResponse>(JsonOptions, ct);
            error = body?.Error;
            detail = body?.Detail;
        }
        catch (Exception)
        {
            // Non-JSON error body: fall through to the generic message below.
        }

        logger.LogError(
            "AI service returned {StatusCode}: {Error} {Detail}",
            (int)response.StatusCode, error, detail);

        throw new AiServiceException(
            error ?? "The AI service could not complete this request.",
            (int)response.StatusCode,
            detail);
    }

    private AiServiceException Unreachable(Exception exception)
    {
        logger.LogError(exception, "AI service is unreachable at {BaseAddress}.", httpClient.BaseAddress);
        return new AiServiceException(
            "AI service is currently unavailable. Please ensure the RAG service and Foundry Local are running.",
            503);
    }
}
