using FinAi.Api.Entities;
using FinAi.Api.Services;
using Microsoft.EntityFrameworkCore;

namespace FinAi.Api.Data;

/// <summary>
/// Applies migrations and resolves the single local user on startup.
/// There is no sign-in: conversations still hang off a user row, so exactly
/// one is created the first time the app runs and reused from then on.
/// </summary>
public static class DbSeeder
{
    private const string LocalEmail = "local@finai.local";

    public static async Task InitialiseAsync(
        IServiceProvider services, IConfiguration configuration, ILogger logger)
    {
        using var scope = services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<FinAiDbContext>();

        await db.Database.MigrateAsync();
        logger.LogInformation("Database schema is up to date.");

        var displayName = configuration.GetValue("LocalUser:DisplayName", "Analyst")!;

        // Any pre-existing row wins, so upgrading from the account-based build
        // keeps the conversations that were already recorded against it.
        var user = await db.Users.OrderBy(candidate => candidate.CreatedAt)
            .FirstOrDefaultAsync();

        if (user is null)
        {
            user = new User { Email = LocalEmail, DisplayName = displayName };
            db.Users.Add(user);
            await db.SaveChangesAsync();
            logger.LogInformation("Created the local user {UserId}.", user.Id);
        }

        scope.ServiceProvider.GetRequiredService<LocalUser>().Id = user.Id;
    }
}
