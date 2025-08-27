# =====================================================
# pages/1_🏠_Property_Search.py
# =====================================================

import streamlit as st
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from utils.auth import initialize_auth_state
from utils.rentcast_api import fetch_property_details
from utils.database import get_user_usage
from streamlit.components.v1 import html
from supabase import create_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Property Search", page_icon="🏠", layout="wide")

# =====================================================
# 1. Supabase Client (using Streamlit secrets)
# =====================================================
SUPABASE_URL = st.secrets["supabase"]["url"]
SUPABASE_KEY = st.secrets["supabase"]["key"]

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase URL or Key not found in Streamlit secrets.toml")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================
# 2. Database Functions (Supabase)
# =====================================================

def save_property_search(user_id: str, property_data: Dict[Any, Any]) -> bool:
    """Save property search to Supabase"""
    try:
        response = supabase.table("property_searches").insert({
            "user_id": user_id,
            "property_data": property_data,
            "search_date": datetime.utcnow().isoformat()
        }).execute()
        return response.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Error saving property search: {e}")
        return False

def get_user_property_searches(user_id: str, limit: int = 50) -> List[Dict]:
    """Fetch user's searches from Supabase"""
    try:
        response = supabase.table("property_searches") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("search_date", desc=True) \
            .limit(limit) \
            .execute()
        return response.data if response.data else []
    except Exception as e:
        logger.error(f"Error fetching property searches: {e}")
        return []

def delete_property_search(search_id: str, user_id: str) -> bool:
    """Delete a specific property search"""
    try:
        response = supabase.table("property_searches") \
            .delete() \
            .eq("id", search_id) \
            .eq("user_id", user_id) \
            .execute()
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error deleting property search: {e}")
        return False

def get_search_statistics(user_id: str) -> Dict[str, Any]:
    """Get user's search statistics"""
    try:
        searches = get_user_property_searches(user_id)
        total_searches = len(searches)
        recent_searches = sum(
            1 for s in searches if datetime.fromisoformat(s['search_date']) >= datetime.utcnow() - timedelta(days=30)
        )
        # Count top property types
        type_counts = {}
        for s in searches:
            prop_type = s['property_data'].get('propertyType')
            if prop_type:
                type_counts[prop_type] = type_counts.get(prop_type, 0) + 1
        top_property_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            'total_searches': total_searches,
            'recent_searches': recent_searches,
            'top_property_types': [{'property_type': k, 'count': v} for k, v in top_property_types]
        }
    except Exception as e:
        logger.error(f"Error getting search statistics: {e}")
        return {}

# =====================================================
# 3. Initialize & Auth
# =====================================================
initialize_auth_state()

if st.session_state.user is None:
    st.warning("⚠️ Please log in from the main page to access this feature.")
    st.stop()

user_email = st.session_state.user.email
user_id = st.session_state.user.id

# =====================================================
# 4. Sidebar (Usage / Limits & Quick Stats)
# =====================================================
with st.sidebar:
    st.subheader("👤 Account Info")
    queries_used = get_user_usage(user_id, user_email)

    st.metric("Email", user_email)
    st.metric("Queries Used", f"{queries_used}/30")

    if queries_used >= 30:
        st.error("🚫 Query limit reached!")
    elif queries_used >= 25:
        st.warning("⚠️ Approaching limit!")

    # Search Statistics
    st.subheader("📊 Search Statistics")
    stats = get_search_statistics(user_id)
    if stats:
        st.metric("Total Searches", stats.get('total_searches', 0))
        st.metric("Last 30 Days", stats.get('recent_searches', 0))
        if stats.get('top_property_types'):
            st.subheader("🏠 Top Property Types")
            for prop_type in stats['top_property_types']:
                st.text(f"{prop_type['property_type']}: {prop_type['count']}")

# =====================================================
# 5. Tab Layout
# =====================================================
tab1, tab2 = st.tabs(["🔍 New Search", "📚 Search History"])

# =====================================================
# 6. Helper Functions
# =====================================================

def safe_get(data, key, default="N/A"):
    try:
        value = data.get(key, default)
        return value if value not in (None, "") else default
    except Exception:
        return default

def format_currency(value):
    try:
        if isinstance(value, (int, float)) and value > 0:
            return f"${value:,.0f}"
        elif isinstance(value, str) and value.replace(',', '').replace('$', '').isdigit():
            return f"${int(value.replace(',', '').replace('$', '')):,}"
        return "N/A"
    except Exception:
        return "N/A"

def build_card(title: str, content: str) -> str:
    return f"""
    <div class="card">
        <h3>{title}</h3>
        <div class="content">{content}</div>
    </div>
    """

def build_compact_card(title: str, content: str, card_id: str = "") -> str:
    return f"""
    <div class="compact-card" id="{card_id}">
        <h4>{title}</h4>
        <div class="compact-content">{content}</div>
    </div>
    """

def process_property_data(raw_data):
    try:
        if isinstance(raw_data, str):
            property_data = json.loads(raw_data)
        elif isinstance(raw_data, (dict, list)):
            property_data = raw_data
        else:
            return None

        properties = []
        if isinstance(property_data, list):
            properties = property_data
        elif isinstance(property_data, dict):
            if "properties" in property_data:
                properties = property_data["properties"]
            elif "data" in property_data:
                properties = property_data["data"]
            elif any(key in property_data for key in ["formattedAddress", "propertyType", "bedrooms", "id"]):
                properties = [property_data]

        if not properties:
            return None
        return properties[0]
    except Exception:
        return None

def render_property_cards(prop: Dict[Any, Any], compact: bool = False) -> str:
    cards_html = ""
    card_function = build_compact_card if compact else build_card

    # Basic info
    basic_info = f"""
    <b>Property Type:</b> {safe_get(prop, 'propertyType')}<br>
    <b>Bedrooms:</b> {safe_get(prop, 'bedrooms')}<br>
    <b>Bathrooms:</b> {safe_get(prop, 'bathrooms')}<br>
    <b>Square Footage:</b> {safe_get(prop, 'squareFootage')} sq ft<br>
    <b>Year Built:</b> {safe_get(prop, 'yearBuilt')}
    """
    cards_html += card_function("🏠 Basic Information", basic_info)

    # Address info
    address_info = f"""
    <b>Full Address:</b> {safe_get(prop, 'formattedAddress', safe_get(prop, 'address'))}<br>
    <b>City:</b> {safe_get(prop, 'city')}<br>
    <b>State:</b> {safe_get(prop, 'state')}<br>
    <b>ZIP Code:</b> {safe_get(prop, 'zipCode')}
    """
    cards_html += card_function("📍 Address", address_info)

    # Valuation
    valuation_info = ""
    estimated_value = safe_get(prop, 'estimatedValue')
    if estimated_value != "N/A":
        valuation_info += f"<b>Estimated Value:</b> {format_currency(estimated_value)}<br>"
    market_value = safe_get(prop, 'marketValue')
    if market_value != "N/A":
        valuation_info += f"<b>Market Value:</b> {format_currency(market_value)}<br>"
    if valuation_info:
        cards_html += card_function("💰 Property Valuation", valuation_info)

    return cards_html

# =====================================================
# 7. NEW SEARCH TAB
# =====================================================
with tab1:
    st.title("🏠 Property Search")
    address = st.text_input("Enter Property Address", placeholder="123 Main St, City, State ZIP")

    if st.button("🔍 Search Property"):
        if not address:
            st.error("Enter a property address")
        else:
            with st.spinner("Fetching property data..."):
                raw_response = fetch_property_details(address, user_id, user_email)
                prop = process_property_data(raw_response)
                if not prop:
                    st.error("No property data found")
                    st.stop()

                property_address = safe_get(prop, 'formattedAddress', address)
                st.success(f"✅ Property found: {property_address}")

                if save_property_search(user_id, prop):
                    st.success("💾 Search saved!")
                else:
                    st.warning("⚠️ Could not save search to history")

                cards_html = render_property_cards(prop)
                html(f"<div class='container'>{cards_html}</div>", height=800, scrolling=True)

# =====================================================
# 8. SEARCH HISTORY TAB
# =====================================================
with tab2:
    st.title("📚 Property Search History")
    search_history = get_user_property_searches(user_id)

    if not search_history:
        st.info("No search history found.")
    else:
        for search in search_history:
            address = safe_get(search['property_data'], 'formattedAddress', 'Unknown Address')
            search_date = datetime.fromisoformat(search['search_date']).strftime("%Y-%m-%d %H:%M:%S")
            cards_html = render_property_cards(search['property_data'], compact=True)
            st.markdown(f"### {address} — {search_date}")
            html(f"<div class='container'>{cards_html}</div>", height=400, scrolling=True)

            if st.button(f"🗑 Delete Search", key=f"del-{search['id']}"):
                if delete_property_search(search['id'], user_id):
                    st.success("Deleted successfully")
                    st.experimental_rerun()
                else:
                    st.error("Failed to delete")

# =====================================================
# 9. CSS STYLING
# =====================================================
st.markdown("""
<style>
.container { display: flex; flex-direction: column; gap: 15px; }
.card, .compact-card { border: 1px solid #ddd; padding: 15px; border-radius: 8px; background: #fafafa; }
.card h3, .compact-card h4 { margin: 0 0 10px 0; }
.compact-card { font-size: 0.9em; }
</style>
""", unsafe_allow_html=True)
