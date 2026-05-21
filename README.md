# PDF to Kindle EPUB Converter (Manga Optimized)

Este projeto é uma aplicação web construída com FastAPI que converte arquivos PDF (especialmente mangás e quadrinhos) para o formato EPUB, otimizado para dispositivos Kindle.

## Características

- **Otimização para Kindle:** Redimensiona imagens para 1448px de altura e converte para tons de cinza.
- **Limite de Tamanho:** Focado em manter o arquivo final abaixo de 50MB (limite do Send-to-Kindle).
- **Processamento Paralelo:** Utiliza múltiplos núcleos da CPU para acelerar a conversão de imagens.
- **Interface Web Simples:** Interface intuitiva com barra de progresso e logs em tempo real.

## Tecnologias Utilizadas

- **FastAPI:** Framework web para o backend.
- **PyMuPDF (fitz):** Para extração e renderização de páginas do PDF.
- **EbookLib:** Para criação do arquivo EPUB.
- **Pillow (PIL):** Para processamento e compressão de imagens.
- **Tailwind CSS:** Para a estilização da interface frontend.

## Pré-requisitos

- Python 3.10 ou superior.

## Instalação

1. Clone o repositório:
   ```bash
   git clone <url-do-repositorio>
   cd pdf-converter
   ```

2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # No Windows: venv\Scripts\activate
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Como Rodar

Para iniciar o servidor, execute o seguinte comando de dentro da pasta raiz:

```bash
cd pdf-to-epub
uvicorn main:app --reload
```

A aplicação estará disponível em `http://127.0.0.1:8000`.

## Estrutura do Projeto

- `pdf-to-epub/main.py`: Lógica do servidor e processamento de conversão.
- `pdf-to-epub/index.html`: Interface do usuário.
- `pdf-to-epub/temp_files/`: Diretório temporário para armazenamento de PDFs enviados e arquivos processados.
- `venv/`: Ambiente virtual Python.

## Notas

- O conversor tenta atingir um alvo de ~200KB por página para garantir que volumes grandes caibam no limite de 50MB do Kindle.
- Se o arquivo final ainda exceder 50MB, considere dividir o PDF original em partes menores.
