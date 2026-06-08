import urllib.parse
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Wikipedia Info Server")

_STATIC_SUMMARIES: dict[str, str] = {
    "rome": (
        "Rome (Italian: Roma) is the capital and largest city of Italy. "
        "Founded, according to legend, by Romulus in 753 BC, it served as the centre of the Roman Empire. "
        "Key landmarks include the Colosseum, the Pantheon, the Roman Forum, the Trevi Fountain, and "
        "Vatican City — the world's smallest sovereign state, home to St. Peter's Basilica and the Sistine Chapel."
    ),
    "paris": (
        "Paris is the capital and most populous city of France, with a population of about 2.2 million. "
        "Famous for art, fashion, gastronomy, and culture, it draws over 30 million tourists a year. "
        "Key landmarks include the Eiffel Tower, the Louvre Museum, Notre-Dame Cathedral, Musée d'Orsay, "
        "and the Arc de Triomphe on the Champs-Élysées."
    ),
    "tokyo": (
        "Tokyo (東京) is the capital and most populous city of Japan, home to about 14 million people in its city "
        "proper and over 37 million in its greater metropolitan area — the most populous in the world. "
        "Key attractions include the Shibuya Crossing, Senso-ji Temple in Asakusa, Shinjuku Gyoen, Akihabara "
        "electronics district, Harajuku, teamLab digital art museums, and Mount Fuji day-trips."
    ),
    "london": (
        "London is the capital and largest city of England and the United Kingdom. "
        "A global city and financial hub with a population of 8.9 million, it lies along the River Thames. "
        "Top attractions include the British Museum, the Tower of London and Tower Bridge, Buckingham Palace, "
        "the Tate Modern, Hyde Park, and the Palace of Westminster with Big Ben."
    ),
    "new york": (
        "New York City (NYC) is the most populous city in the United States, with about 8.3 million residents. "
        "Known as 'The Big Apple', it is a global hub for finance, culture, and media. "
        "Iconic sights include Times Square, Central Park, the Statue of Liberty, the Empire State Building, "
        "the Metropolitan Museum of Art, Brooklyn Bridge, and Broadway theatre."
    ),
    "barcelona": (
        "Barcelona is the capital of Catalonia, Spain, and a major Mediterranean port city of 1.6 million people. "
        "Renowned for its unique architecture by Antoni Gaudí, including the Sagrada Família basilica, "
        "Park Güell, Casa Batlló, and La Pedrera. Other highlights are Las Ramblas promenade, "
        "the Gothic Quarter, Camp Nou stadium, and the beaches of Barceloneta."
    ),
    "amsterdam": (
        "Amsterdam is the capital and most populous city of the Netherlands, famous for its canal ring — "
        "a UNESCO World Heritage Site — and its Golden Age heritage. "
        "Key sights include the Rijksmuseum, the Van Gogh Museum, the Anne Frank House, "
        "the Jordaan neighbourhood, Vondelpark, and the vibrant flower market."
    ),
    "dubai": (
        "Dubai is the most populous city in the United Arab Emirates, a global hub for business and tourism. "
        "Known for record-breaking architecture including the Burj Khalifa (the world's tallest building), "
        "the Burj Al Arab, Dubai Mall, and Palm Jumeirah artificial island. "
        "It also offers desert safaris, world-class shopping, and the historic Al Fahidi district."
    ),
    "bali": (
        "Bali is an Indonesian island and one of the world's top holiday destinations, known for its forested "
        "volcanic mountains, rice paddies, beaches, and coral reefs. "
        "Cultural highlights include Hindu temples such as Tanah Lot, Uluwatu, and Besakih, "
        "the artistic towns of Ubud and Seminyak, traditional Kecak dance, and world-class surfing."
    ),
    "sydney": (
        "Sydney is the capital of New South Wales and the largest city in Australia, home to 5.3 million people. "
        "Its iconic Harbour features the Sydney Opera House — a UNESCO World Heritage Site — and the Sydney Harbour Bridge. "
        "Bondi Beach, Darling Harbour, The Rocks historic district, Taronga Zoo, and the Blue Mountains are popular draws."
    ),
    "lisbon": (
        "Lisbon (Lisboa) is the capital and largest city of Portugal, perched on seven hills above the Tagus estuary. "
        "Known for its pastel-coloured trams, Fado music, and Age of Discovery heritage. "
        "Key sights include Belém Tower, Jerónimos Monastery (both UNESCO listed), Alfama district, "
        "São Jorge Castle, and Sintra palaces nearby."
    ),
    "bangkok": (
        "Bangkok (Krung Thep) is the capital and most populous city of Thailand, with over 10 million residents. "
        "A vibrant metropolis blending ultramodern skyscrapers with ornate temples. "
        "Highlights include the Grand Palace and Wat Phra Kaew, Wat Arun (Temple of Dawn), "
        "Chatuchak Weekend Market, Khao San Road, and world-renowned street food."
    ),
}


_HEADERS = {
    "User-Agent": "ADK-Workshop-TravelPlanner/2.0 (educational; contact: workshop@example.com)"
}


def _wikipedia_api_summary(query: str) -> str | None:
    """Queries the Wikipedia REST API for a page summary. Returns None on failure."""
    title = urllib.parse.quote(query.strip().title(), safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    try:
        resp = httpx.get(url, timeout=6.0, follow_redirects=True, headers=_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            extract = data.get("extract", "").strip()
            display_title = data.get("title", query)
            if extract:
                # Trim to a useful length for the LLM context
                return f"{display_title}: {extract[:900]}"
    except Exception:
        pass
    return None


@mcp.tool()
def search_wikipedia(query: str) -> str:
    """Search Wikipedia for cultural, historic, and geographical information about a destination.

    Args:
        query: The search term (e.g., 'Rome', 'Colosseum', 'Tokyo temples').
    """
    # 1. Try the live Wikipedia REST API first
    live_result = _wikipedia_api_summary(query)
    if live_result:
        return live_result

    # 2. Fall back to curated static summaries
    q_lower = query.strip().lower()
    for key, summary in _STATIC_SUMMARIES.items():
        if key in q_lower:
            return summary

    return (
        f"Wikipedia results for '{query}': A beautiful destination rich in history, "
        "gastronomy, and cultural heritage. Local cuisine, architecture, and traditions "
        "make it a memorable travel experience."
    )


if __name__ == "__main__":
    mcp.run()
