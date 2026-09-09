using System.Text.Json;
using FinRag.Api.DTOs;
using FinRag.Api.Services;

namespace FinRag.Api.Middleware;

/// <summary>
/// Converts exceptions into the uniform <see cref="ApiError"/> envelope.
/// Internal detail is logged, never returned: clients see an actionable
/// sentence, and stack traces stay on the server.
/// </summary>
public class ExceptionHandlingMiddleware(
    RequestDelegate next, ILogger<ExceptionHandlingMiddleware> logger)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (DomainException exception)
        {
            // Expected, user-correctable: the message is safe to return.
            logger.LogInformation("Rejected request: {Message}", exception.Message);
            await WriteAsync(context, exception.StatusCode, new ApiError(exception.Message));
        }
        catch (AiServiceException exception)
        {
            logger.LogError(exception, "AI service call failed.");
            await WriteAsync(
                context,
                exception.StatusCode is >= 400 and < 600 ? exception.StatusCode : 503,
                new ApiError(exception.Message, exception.Detail));
        }
        catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested)
        {
            // The client went away; there is nobody left to answer.
            logger.LogInformation("Request cancelled by the client.");
        }
        catch (Exception exception)
        {
            logger.LogError(exception, "Unhandled exception processing {Path}.", context.Request.Path);
            await WriteAsync(
                context,
                StatusCodes.Status500InternalServerError,
                new ApiError("An unexpected error occurred while processing the request."));
        }
    }

    private static async Task WriteAsync(HttpContext context, int statusCode, ApiError error)
    {
        if (context.Response.HasStarted)
        {
            // Too late to change the response; the logs already carry the cause.
            return;
        }

        context.Response.Clear();
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsync(JsonSerializer.Serialize(error, Json));
    }
}
