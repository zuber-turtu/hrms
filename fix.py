import glob
import re

for f in glob.glob('app/routers/*.py'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
        
    # Find all TemplateResponse calls
    # We want to change templates.TemplateResponse("some/file.html", {...})
    # to templates.TemplateResponse(request=request, name="some/file.html", context={...})
    
    content = re.sub(
        r'templates\.TemplateResponse\(\s*(["\'][^"\']+["\'])\s*,\s*(\{.*?\})\s*\)',
        r'templates.TemplateResponse(request=request, name=\1, context=\2)',
        content,
        flags=re.DOTALL
    )
    
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
    print(f'Fixed {f}')
