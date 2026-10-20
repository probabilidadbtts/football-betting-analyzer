import os
from google import genai

# Configurar la API Key desde los secretos de GitHub Actions
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("No se encontró la GEMINI_API_KEY en el entorno.")

# Inicializar el cliente oficial con la nueva librería google-genai
client = genai.Client(api_key=api_key)

# Archivos críticos de tu sistema de inversión que la IA va a optimizar
files_to_optimize = [
    "src/analyzer.py",
    "src/markets/value.py",
    "src/kelly.py",
    "src/config.py"
]

system_instruction = """
Eres un Ingeniero Quant Senior y experto en sistemas automatizados de inversión deportiva. 
Tu objetivo es refactorizar, auditar y optimizar el código Python proporcionado para maximizar:
1. La precisión estadística y matemática (cálculos de xG, modelos de Poisson, Criterio de Kelly).
2. La robustez ante fallos de red, datos nulos o respuestas vacías de APIs (control de errores estricto).
3. La limpieza, tipado estricto y eficiencia en la ejecución concurrente.
Devuelve ÚNICAMENTE el código Python limpio, completo y listo para producción, sin explicaciones adicionales fuera del código.
"""

for filepath in files_to_optimize:
    if os.path.exists(filepath):
        print(f"-> Analizando y optimizando {filepath} con Gemini 3.8 Flash...")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        prompt = f"{system_instruction}\n\nCódigo actual del archivo `{filepath}`:\n```python\n{content}\n```\nEntraga la versión mejorada completa."
        
        # Nueva sintaxis de llamada para Gemini 3.8 Flash con google-genai
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
        )
        optimized_code = response.text
        
        # Limpiar etiquetas de Markdown si el modelo las incluye en la respuesta
        if "```python" in optimized_code:
            parts = optimized_code.split("```python")
            if len(parts) > 1:
                optimized_code = parts[1].split("```")[0].strip()
        elif "```" in optimized_code:
            parts = optimized_code.split("```")
            if len(parts) > 1:
                optimized_code = parts[1].strip()

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(optimized_code)
        print(f"-> ¡{filepath} optimizado y guardado con éxito!")
    else:
        print(f"-> El archivo {filepath} no existe, se omite.")
