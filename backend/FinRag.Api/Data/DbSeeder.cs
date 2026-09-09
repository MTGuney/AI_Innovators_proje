using FinRag.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinRag.Api.Data;

/// <summary>Applies migrations and seeds the demo account on startup.</summary>
public static class DbSeeder
{
    public static async Task InitialiseAsync(
        IServiceProvider services, IConfiguration configuration, ILogger logger)
    {
        using var scope = services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<FinRagDbContext>();

        await db.Database.MigrateAsync();
        logger.LogInformation("Database schema is up to date.");

        if (!configuration.GetValue("Seed:DemoUser", true))
        {
            return;
        }

        var email = configuration.GetValue("Seed:DemoUserEmail", "demo@finrag.local")!
            .ToLowerInvariant();

        if (await db.Users.AnyAsync(user => user.Email == email))
        {
            return;
        }

        var password = configuration.GetValue("Seed:DemoUserPassword", "demo12345")!;
        db.Users.Add(new User
        {
            Email = email,
            DisplayName = "Demo Analyst",
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(password)
        });

        await db.SaveChangesAsync();
        logger.LogInformation("Seeded demo user {Email}.", email);
    }
}
