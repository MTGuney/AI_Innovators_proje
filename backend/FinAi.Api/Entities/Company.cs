namespace FinAi.Api.Entities;

/// <summary>A company whose reports are held in the corpus.</summary>
public class Company
{
    public Guid Id { get; set; } = Guid.NewGuid();

    public string Name { get; set; } = string.Empty;

    public string? Ticker { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public ICollection<FinancialReport> Reports { get; set; } = new List<FinancialReport>();
}
