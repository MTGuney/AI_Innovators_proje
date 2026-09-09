using System.Text;
using FinRag.Api.Configuration;
using FinRag.Api.Data;
using FinRag.Api.Middleware;
using FinRag.Api.Repositories;
using FinRag.Api.Services;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);

// --------------------------------------------------------------------- //
// Configuration
// --------------------------------------------------------------------- //

builder.Services.Configure<AiServiceOptions>(
    builder.Configuration.GetSection(AiServiceOptions.SectionName));
builder.Services.Configure<JwtOptions>(
    builder.Configuration.GetSection(JwtOptions.SectionName));

var jwt = builder.Configuration.GetSection(JwtOptions.SectionName).Get<JwtOptions>()
          ?? new JwtOptions();

if (jwt.Secret.Length < 32)
{
    // Refuse to start rather than issue tokens signed with a weak key.
    throw new InvalidOperationException(
        "Jwt:Secret must be at least 32 characters. Set it via configuration or the JWT_SECRET environment variable.");
}

// --------------------------------------------------------------------- //
// Persistence
// --------------------------------------------------------------------- //

var connectionString = builder.Configuration.GetConnectionString("Default")
                       ?? throw new InvalidOperationException(
                           "No 'Default' connection string configured (DATABASE_URL).");

builder.Services.AddDbContext<FinRagDbContext>(options =>
    options.UseNpgsql(connectionString));

// --------------------------------------------------------------------- //
// Application services
// --------------------------------------------------------------------- //

builder.Services.AddScoped<IUserRepository, UserRepository>();
builder.Services.AddScoped<ICompanyRepository, CompanyRepository>();
builder.Services.AddScoped<IReportRepository, ReportRepository>();
builder.Services.AddScoped<IConversationRepository, ConversationRepository>();

builder.Services.AddScoped<IAuthService, AuthService>();
builder.Services.AddScoped<IReportService, ReportService>();
builder.Services.AddScoped<IChatService, ChatService>();
builder.Services.AddScoped<IDashboardService, DashboardService>();

var aiOptions = builder.Configuration.GetSection(AiServiceOptions.SectionName)
                    .Get<AiServiceOptions>() ?? new AiServiceOptions();

builder.Services.AddHttpClient<IAiServiceClient, AiServiceClient>(client =>
{
    client.BaseAddress = new Uri(aiOptions.BaseUrl);
    // Local generation is slow; a short timeout would abort valid answers.
    client.Timeout = TimeSpan.FromSeconds(aiOptions.TimeoutSeconds);
});

// --------------------------------------------------------------------- //
// Authentication
// --------------------------------------------------------------------- //

builder.Services
    .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = jwt.Issuer,
            ValidAudience = jwt.Audience,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwt.Secret)),
            ClockSkew = TimeSpan.FromMinutes(1)
        };
    });

builder.Services.AddAuthorization();

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
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();

app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "finrag-backend" }))
    .AllowAnonymous();

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
