# syntax=docker/dockerfile:1

# --- Build ---------------------------------------------------------------- #
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build

WORKDIR /src

# Restore against the project file alone so code edits reuse the package layer.
COPY FinRag.Api/FinRag.Api.csproj FinRag.Api/
RUN dotnet restore FinRag.Api/FinRag.Api.csproj

COPY . .
RUN dotnet publish FinRag.Api/FinRag.Api.csproj -c Release -o /app/publish --no-restore

# --- Runtime -------------------------------------------------------------- #
FROM mcr.microsoft.com/dotnet/aspnet:9.0 AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/publish ./

# Uploaded reports are shared with the AI service through a volume.
RUN mkdir -p /app/uploads

ENV ASPNETCORE_URLS=http://0.0.0.0:8080 \
    ASPNETCORE_ENVIRONMENT=Production

RUN useradd --create-home --uid 1001 finrag && chown -R finrag:finrag /app
USER finrag

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

ENTRYPOINT ["dotnet", "FinRag.Api.dll"]
