from mcp.server.fastmcp import FastMCP

# Create a FastMCP instance representing our travel service
mcp = FastMCP("Travel API Server")

@mcp.tool()
def search_flights(destination: str, dates: str) -> str:
    """Search for available flights to a destination on specific dates.
    
    Args:
        destination: The target city or airport code.
        dates: The travel dates (e.g. 'June 10-15').
    """
    return (
        f"Available Flights to {destination} ({dates}):\n"
        f"1. Flight FL-101 (Direct) - Price: $350 - Departure: 08:00 AM\n"
        f"2. Flight FL-202 (1 Stop) - Price: $220 - Departure: 02:00 PM\n"
    )

@mcp.tool()
def search_hotels(destination: str, dates: str) -> str:
    """Search for available hotels or Airbnb properties at the destination.
    
    Args:
        destination: The target city.
        dates: The check-in and check-out dates.
    """
    return (
        f"Available Accommodations in {destination} ({dates}):\n"
        f"1. Seaside Villa (ID: 501) - Price: $150/night - Rating: 4.8/5\n"
        f"2. Cozy Downtown Loft (ID: 502) - Price: $80/night - Rating: 4.5/5\n"
        f"3. Budget Backpacker Hostel (ID: 503) - Price: $30/night - Rating: 4.1/5\n"
    )

@mcp.tool()
def confirm_booking(hotel_id: int, flight_id: str) -> str:
    """Confirm and book the selected hotel and flight.
    
    Args:
        hotel_id: The ID of the hotel to book.
        flight_id: The code/ID of the flight to book.
    """
    return f"Booking confirmed for Hotel #{hotel_id} and Flight {flight_id}! Confirmation Code: TRV-99824X"

if __name__ == "__main__":
    # Start the MCP server via stdio transport
    mcp.run()
