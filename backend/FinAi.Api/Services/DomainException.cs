namespace FinAi.Api.Services;

/// <summary>Raised for expected, user-correctable problems.</summary>
public class DomainException(string message, int statusCode = 400) : Exception(message)
{
    public int StatusCode { get; } = statusCode;
}
