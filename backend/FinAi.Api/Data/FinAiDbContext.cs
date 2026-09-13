using FinAi.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinAi.Api.Data;

/// <summary>
/// PostgreSQL persistence for users, report metadata and chat history.
/// Embeddings deliberately live only in ChromaDB and are never duplicated here.
/// </summary>
public class FinAiDbContext(DbContextOptions<FinAiDbContext> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();

    public DbSet<Company> Companies => Set<Company>();

    public DbSet<FinancialReport> Reports => Set<FinancialReport>();

    public DbSet<Conversation> Conversations => Set<Conversation>();

    public DbSet<Message> Messages => Set<Message>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<User>(entity =>
        {
            entity.HasIndex(user => user.Email).IsUnique();
            entity.Property(user => user.Email).HasMaxLength(256).IsRequired();
            entity.Property(user => user.DisplayName).HasMaxLength(128).IsRequired();
        });

        modelBuilder.Entity<Company>(entity =>
        {
            entity.HasIndex(company => company.Name).IsUnique();
            entity.Property(company => company.Name).HasMaxLength(200).IsRequired();
            entity.Property(company => company.Ticker).HasMaxLength(16);
        });

        modelBuilder.Entity<FinancialReport>(entity =>
        {
            entity.Property(report => report.Title).HasMaxLength(400).IsRequired();
            entity.Property(report => report.ReportType).HasMaxLength(40).IsRequired();
            entity.Property(report => report.FileName).HasMaxLength(400).IsRequired();
            entity.Property(report => report.DocumentId).HasMaxLength(200);
            entity.Property(report => report.IndexStatus).HasConversion<string>().HasMaxLength(20);

            entity.HasIndex(report => report.DocumentId);
            entity.HasIndex(report => new { report.CompanyId, report.Year, report.ReportType });

            entity.HasOne(report => report.Company)
                .WithMany(company => company.Reports)
                .HasForeignKey(report => report.CompanyId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Conversation>(entity =>
        {
            entity.Property(conversation => conversation.Title).HasMaxLength(300).IsRequired();
            entity.HasIndex(conversation => new { conversation.UserId, conversation.UpdatedAt });

            entity.HasOne(conversation => conversation.User)
                .WithMany(user => user.Conversations)
                .HasForeignKey(conversation => conversation.UserId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Message>(entity =>
        {
            entity.Property(message => message.Role).HasConversion<string>().HasMaxLength(16);
            entity.Property(message => message.Confidence).HasMaxLength(16);
            entity.Property(message => message.Model).HasMaxLength(120);
            entity.HasIndex(message => new { message.ConversationId, message.CreatedAt });

            entity.HasOne(message => message.Conversation)
                .WithMany(conversation => conversation.Messages)
                .HasForeignKey(message => message.ConversationId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
