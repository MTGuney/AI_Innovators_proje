namespace FinRag.Api.Services;

/// <summary>
/// The single local user this instance runs as. FinRAG is a local-first,
/// single-user tool, so there is no sign-in and nothing to authenticate --
/// conversations are still owned by a user row, and this holds that row's id.
/// Populated once at startup by <see cref="Data.DbSeeder"/>.
/// </summary>
public class LocalUser
{
    public Guid Id { get; set; }
}
