import os
import json
import re
import streamlit as st
import requests
import tempfile
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from pydantic import BaseModel, Field
from fpdf import FPDF

# ==============================================================================
# SECTION 1: SETUP & CONFIGURATION
# ==============================================================================

load_dotenv()

st.set_page_config(
    page_title="AI Recipe Architect",
    page_icon="👨‍🍳",
    layout="wide"
)

llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", temperature=0.7)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# ==============================================================================
# SECTION 2: TOOLS (LLM & IMAGE)
# ==============================================================================

class RecipeInput(BaseModel):
    ingredients: str = Field(description="A comma-separated list of ingredients.")
    dietary_needs: str = Field(description="Dietary restrictions (e.g., Vegan, Gluten-Free).")

@tool
def create_recipe(ingredients: str, dietary_needs: str) -> str:
    """
    Generates a unique recipe based on the given ingredients and dietary needs.
    Returns a JSON string with title, description, ingredients, instructions, and image keywords.
    """
    prompt = f"""
    You are a creative chef. Create a unique and delicious recipe using the following ingredients: {ingredients}.
    The recipe must adhere to these dietary restrictions: {dietary_needs}.
    
    Respond as a JSON object with:
    - "title"
    - "description"
    - "ingredients" (array of strings)
    - "instructions" (array of strings)
    - "image_keywords"
    """
    try:
        response = llm.invoke(prompt)
        json_content = response.content.replace('```json', '').replace('```', '').strip()
        json.loads(json_content)
        return json_content
    except Exception as e:
        st.error(f"Error generating recipe: {e}")
        return json.dumps({
            "title": "Failed to generate recipe",
            "description": "Please try again.",
            "ingredients": [],
            "instructions": [],
            "image_keywords": ""
        })

@tool
def get_nutritional_info(recipe_text: str) -> str:
    """
    Estimates nutritional information (calories, protein, fat, carbs, summary) per serving 
    for the given recipe text. Returns a JSON string.
    """
    prompt = f"""
    Estimate the nutritional breakdown per serving for this recipe:
    {recipe_text}
    
    Respond as JSON:
    - "calories"
    - "protein_grams"
    - "fat_grams"
    - "carbs_grams"
    - "summary"
    """
    try:
        response = llm.invoke(prompt)
        json_content = response.content.replace('```json', '').replace('```', '').strip()
        json.loads(json_content)
        return json_content
    except Exception as e:
        st.error(f"Error generating nutritional info: {e}")
        return json.dumps({
            "calories": 0, "protein_grams": 0, "fat_grams": 0, "carbs_grams": 0,
            "summary": "Nutritional info unavailable."
        })

@tool
def generate_recipe_image(image_keywords: str) -> str:
    """
    Searches for a recipe image using the Pexels API based on the given keywords. 
    Returns the image URL (or a fallback image if unavailable).
    """
    fallback_image = "https://images.pexels.com/photos/1640777/pexels-photo-1640777.jpeg"
    if not PEXELS_API_KEY:
        return fallback_image
    try:
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": image_keywords, "orientation": "landscape", "per_page": 1}
        response = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data["photos"]:
            return data["photos"][0]["src"]["original"]
        else:
            return fallback_image
    except:
        return fallback_image

# ==============================================================================
# SECTION 3: PDF GENERATION
# ==============================================================================

class PDF(FPDF):
    def header(self):
        self.set_font('DejaVuSansCondensed', 'B', 16)
        self.cell(0, 10, 'AI Recipe Architect', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVuSansCondensed', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def create_recipe_pdf(recipe_data, nutrition_data, image_url):
    pdf = PDF('P', 'mm', 'A4')

    # Fonts
    pdf.add_font("DejaVuSansCondensed", "", "DejaVuSansCondensed.ttf", uni=True)
    pdf.add_font("DejaVuSansCondensed", "B", "DejaVuSansCondensed-Bold.ttf", uni=True)
    pdf.add_font("DejaVuSansCondensed", "I", "DejaVuSansCondensed-Oblique.ttf", uni=True)

    pdf.add_page()

    # Title
    pdf.set_font('DejaVuSansCondensed', 'B', 22)
    pdf.multi_cell(0, 12, recipe_data['title'], align='C')
    pdf.ln(4)

    # Description
    pdf.set_font('DejaVuSansCondensed', 'I', 12)
    pdf.multi_cell(0, 8, f"\"{recipe_data['description']}\"", align='C')
    pdf.ln(8)

    # Image
    image_path = None
    try:
        image_response = requests.get(image_url, stream=True, timeout=5)
        if image_response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_file.write(image_response.content)
                image_path = tmp_file.name
            pdf.image(image_path, x=30, w=150)
            pdf.ln(10)
    finally:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)

    # Nutrition
    pdf.set_font('DejaVuSansCondensed', 'B', 14)
    pdf.cell(0, 10, 'Nutritional Information (per serving)', 0, 1, 'C')
    pdf.set_font('DejaVuSansCondensed', '', 12)
    pdf.multi_cell(0, 8, f"Summary: {nutrition_data['summary']}", align='C')
    pdf.ln(4)
    info_line = f"Calories: {nutrition_data['calories']}   Protein: {nutrition_data['protein_grams']}g   Fat: {nutrition_data['fat_grams']}g   Carbs: {nutrition_data['carbs_grams']}g"
    pdf.multi_cell(0, 8, info_line, align='C')
    pdf.ln(10)

    # Ingredients
    pdf.set_font('DejaVuSansCondensed', 'B', 14)
    pdf.cell(0, 10, 'Ingredients', 0, 1)
    pdf.set_font('DejaVuSansCondensed', '', 12)
    for item in recipe_data['ingredients']:
        pdf.multi_cell(0, 8, f"• {item}")
    pdf.ln(8)

    # Instructions
    pdf.set_font('DejaVuSansCondensed', 'B', 14)
    pdf.cell(0, 10, 'Instructions', 0, 1)
    pdf.set_font('DejaVuSansCondensed', '', 12)
    for i, step in enumerate(recipe_data['instructions'], 1):
        clean_step = re.sub(r"^[0-9]+[.)\s]+", "", step).strip()
        pdf.multi_cell(0, 8, f"{i}. {clean_step}")
        pdf.ln(1)

    return pdf.output(dest="S").encode("latin1")

# ==============================================================================
# SECTION 4: STREAMLIT APP
# ==============================================================================

if "recipe_data" not in st.session_state:
    st.session_state.recipe_data = None
if "nutrition_data" not in st.session_state:
    st.session_state.nutrition_data = None
if "image_url" not in st.session_state:
    st.session_state.image_url = None

st.title("AI Recipe Architect 🍳")
st.markdown("### Create unique recipes from your ingredients and dietary needs.")

with st.container(border=True):
    st.header("1. Enter Ingredients", divider='gray')
    ingredients = st.text_input("Ingredients", placeholder="e.g., chicken, broccoli, pasta, garlic")
    dietary_needs = st.selectbox("Dietary Needs (optional)", ["None", "Vegetarian", "Vegan", "Gluten-Free"])
    
    if st.button("Generate My Recipe!", use_container_width=True, type="primary"):
        if not ingredients:
            st.warning("Please enter at least one ingredient.")
        else:
            with st.spinner("Cooking up your recipe..."):
                try:
                    recipe_json_str = create_recipe.run(tool_input={"ingredients": ingredients, "dietary_needs": dietary_needs})
                    recipe_data = json.loads(recipe_json_str)
                    st.session_state.recipe_data = recipe_data
                    
                    image_url = generate_recipe_image.run(tool_input={"image_keywords": recipe_data['image_keywords']})
                    st.session_state.image_url = image_url

                    nutrition_json_str = get_nutritional_info.run(tool_input={"recipe_text": json.dumps(recipe_data)})
                    nutrition_data = json.loads(nutrition_json_str)
                    st.session_state.nutrition_data = nutrition_data

                except Exception as e:
                    st.error(f"An error occurred: {e}")

if st.session_state.recipe_data:
    st.markdown("---")
    st.header("2. Your Custom Recipe")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.image(st.session_state.image_url, caption=st.session_state.recipe_data['title'], use_container_width=True)
    with col2:
        st.markdown("##### Nutritional Information (per serving)")
        st.write(f"**Calories:** {st.session_state.nutrition_data['calories']}")
        st.write(f"**Protein:** {st.session_state.nutrition_data['protein_grams']}g")
        st.write(f"**Fat:** {st.session_state.nutrition_data['fat_grams']}g")
        st.write(f"**Carbs:** {st.session_state.nutrition_data['carbs_grams']}g")
        st.write(f"**Summary:** {st.session_state.nutrition_data['summary']}")
    
    st.markdown("---")
    st.subheader(st.session_state.recipe_data['title'])
    st.write(st.session_state.recipe_data['description'])
    
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("#### Ingredients")
        for ingredient in st.session_state.recipe_data['ingredients']:
            st.markdown(f"- {ingredient}")
    with col4:
        st.markdown("#### Instructions")
        for i, instruction in enumerate(st.session_state.recipe_data['instructions'], 1):
            clean_instruction = re.sub(r"^[0-9]+[.)\s]+", "", instruction).strip()
            st.markdown(f"{i}. {clean_instruction}")
    
    pdf_bytes = create_recipe_pdf(
        st.session_state.recipe_data,
        st.session_state.nutrition_data,
        st.session_state.image_url
    )
    
    st.markdown("---")
    st.download_button(
        label="Download Recipe as PDF",
        data=pdf_bytes,
        file_name=f"{re.sub(r'[^a-zA-Z0-9]', '_', st.session_state.recipe_data['title'])}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
