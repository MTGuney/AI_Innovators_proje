using FinAi.Api.Configuration;
using FinAi.Api.Data;
using FinAi.Api.Middleware;
using FinAi.Api.Repositories;
using FinAi.Api.Services;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// --------------------------------------------------------------------- //
// Configuration
// --------------------------------------------------------------------- //

builder.Services.Configure<AiServiceOptions>(
    builder.Configuration.GetSection(AiServiceOptions.SectionName));

// --------------------------------------------------------------------- //
// Persistence
// --------------------------------------------------------------------- //

var connectionString = builder.Configuration.GetConnectionString("Default")
                       ?? throw new InvalidOperationException(
                           "No 'Default' connection string configured (DATABASE_URL).");

builder.Services.AddDbContext<FinAiDbContext>(options =>
    options.UseNpgsql(connectionString));

// --------------------------------------------------------------------- //
// Application services
// --------------------------------------------------------------------- //

builder.Services.AddScoped<ICompanyRepository, CompanyRepository>();
builder.Services.AddScoped<IReportRepository, ReportRepository>();
builder.Services.AddScoped<IConversationRepository, ConversationRepository>();

// Single-user tool: one user row owns everything, resolved once at startup.
builder.Services.AddSingleton<LocalUser>();

builder.Services.AddScoped<IReportService, ReportService>();
builder.Services.AddScoped<IChatService, ChatService>();
builder.Services.AddScoped<IIndexService, IndexService>();

var aiOptions = builder.Configuration.GetSection(AiServiceOptions.SectionName)
                    .Get<AiServiceOptions>() ?? new AiServiceOptions();

builder.Services.AddHttpClient<IAiServiceClient, AiServiceClient>(client =>
{
    client.BaseAddress = new Uri(aiOptions.BaseUrl);
    // Local generation is slow; a short timeout would abort valid answers.
    client.Timeout = TimeSpan.FromSeconds(aiOptions.TimeoutSeconds);
});

// --------------------------------------------------------------------- //
// Web
// --------------------------------------------------------------------- //

const string CorsPolicy = "frontend";
var allowedOrigins = builder.Configuration
    .GetSection("Cors:AllowedOrigins").Get<string[]>()
    ?? ["http://localhost:5173"];

builder.Services.AddCors(options =>
    options.AddPolicy(CorsPolicy, policy => policy
        .WithOrigins(allowedOrigins)
        .AllowAnyHeader()
        .AllowAnyMethod()));

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Our envelope must wrap everything, so it goes first in the pipeline.
app.UseMiddleware<ExceptionHandlingMiddleware>();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseCors(CorsPolicy);
app.MapControllers();

app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "finai-backend" }));

// --------------------------------------------------------------------- //
// Startup
// --------------------------------------------------------------------- //

var logger = app.Services.GetRequiredService<ILogger<Program>>();
try
{
    await DbSeeder.InitialiseAsync(app.Services, app.Configuration, logger);
}
catch (Exception exception)
{
    // Without a schema nothing works, so surface the cause clearly and stop.
    logger.LogCritical(exception, "Database initialisation failed.");
    throw;
}

app.Run();
