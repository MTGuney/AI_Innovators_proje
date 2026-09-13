using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace FinAi.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddUnsupportedFigures : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "UnsupportedFiguresJson",
                table: "Messages",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "UnsupportedFiguresJson",
                table: "Messages");
        }
    }
}
