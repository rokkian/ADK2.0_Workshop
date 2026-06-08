from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Airbnb Search Server")

@mcp.tool()
def search_airbnb_listings(location: str, price_min: float = 0, price_max: float = 1000) -> str:
    """Search Airbnb properties and listings matching location and budget range.
    
    Args:
        location: Target location name.
        price_min: Minimum budget limit.
        price_max: Maximum budget limit.
    """
    return (
        f"Airbnb listings in {location} between ${price_min} and ${price_max}/night:\n"
        f"1. Historic Center Loft - $95/night - Rating: 4.9 (Superhost)\n"
        f"2. Trastevere Terrace Apartment - $120/night - Rating: 4.8\n"
        f"3. Quiet Studio near Vatican - $60/night - Rating: 4.7"
    )

if __name__ == "__main__":
    mcp.run()
