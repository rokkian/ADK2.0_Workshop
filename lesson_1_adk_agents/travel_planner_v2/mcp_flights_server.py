from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Flights Database Server")

@mcp.tool()
def search_flights_data(origin: str, destination: str, dates: str) -> str:
    """Find available flights, filter by time, and get details.
    
    Args:
        origin: The departure airport code or city.
        destination: The arrival airport code or city.
        dates: Travel dates.
    """
    return (
        f"Flights from {origin} to {destination} ({dates}):\n"
        f"- Flight AZ-402 (Alitalia): Departs 10:00 AM, Price $290 (Direct, Eco)\n"
        f"- Flight LH-108 (Lufthansa): Departs 02:30 PM, Price $210 (1 Layover in FRA, Eco)\n"
        f"- Flight BA-909 (British Airways): Departs 06:15 PM, Price $340 (Direct, Eco)"
    )

if __name__ == "__main__":
    mcp.run()
