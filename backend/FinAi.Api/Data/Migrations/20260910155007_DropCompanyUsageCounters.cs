using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace FinAi.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class DropCompanyUsageCounters : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "LastQueriedAt",
                table: "Companies");

            migrationBuilder.DropColumn(
                name: "QueryCount",
                table: "Companies");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "LastQueriedAt",
                table: "Companies",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "QueryCount",
                table: "Companies",
                type: "integer",
                nullable: false,
                defaultValue: 0);
        }
    }
}
