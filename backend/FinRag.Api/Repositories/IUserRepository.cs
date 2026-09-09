using FinRag.Api.Data;
using FinRag.Api.Entities;
using Microsoft.EntityFrameworkCore;

namespace FinRag.Api.Repositories;

public interface IUserRepository
{
    Task<User?> GetByEmailAsync(string email, CancellationToken ct = default);

    Task<User?> GetByIdAsync(Guid id, CancellationToken ct = default);

    Task<bool> ExistsAsync(string email, CancellationToken ct = default);

    Task<User> AddAsync(User user, CancellationToken ct = default);
}

public class UserRepository(FinRagDbContext db) : IUserRepository
{
    public Task<User?> GetByEmailAsync(string email, CancellationToken ct = default) =>
        db.Users.FirstOrDefaultAsync(user => user.Email == email.ToLowerInvariant(), ct);

    public Task<User?> GetByIdAsync(Guid id, CancellationToken ct = default) =>
        db.Users.FirstOrDefaultAsync(user => user.Id == id, ct);

    public Task<bool> ExistsAsync(string email, CancellationToken ct = default) =>
        db.Users.AnyAsync(user => user.Email == email.ToLowerInvariant(), ct);

    public async Task<User> AddAsync(User user, CancellationToken ct = default)
    {
        db.Users.Add(user);
        await db.SaveChangesAsync(ct);
        return user;
    }
}
