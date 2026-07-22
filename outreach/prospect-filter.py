import csv
import sys

def filter_prospects(input_file, output_file):
    """
    Filtra uma lista de clínicas (geralmente gerada por web scraper) e retém apenas o ICP:
    - Estado no Nordeste (CE, PE, PB, RN, BA, AL, SE, PI, MA)
    - Nicho: Estética Avançada, Dermatologia, Harmonização
    """
    
    # Estados alvo (Nordeste)
    nordeste_uf = ['CE', 'PE', 'PB', 'RN', 'BA', 'AL', 'SE', 'PI', 'MA']
    
    # Palavras-chave do nicho ICP
    keywords_nicho = ['estética', 'estetica', 'harmonização', 'harmonizacao', 'dermatologia', 'botox']
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f_in, \
             open(output_file, 'w', encoding='utf-8', newline='') as f_out:
             
            reader = csv.DictReader(f_in)
            
            # Garante que os headers existem, se não, pode ajustar conforme o input
            headers = reader.fieldnames
            writer = csv.DictWriter(f_out, fieldnames=headers)
            writer.writeheader()
            
            count_total = 0
            count_aprovado = 0
            
            for row in reader:
                count_total += 1
                
                estado = str(row.get('estado', '')).upper()
                bio = str(row.get('bio', '')).lower()
                nome = str(row.get('nome', '')).lower()
                
                # Check Região
                if estado not in nordeste_uf:
                    continue
                    
                # Check Nicho
                is_icp = False
                for kw in keywords_nicho:
                    if kw in bio or kw in nome:
                        is_icp = True
                        break
                        
                if is_icp:
                    writer.writerow(row)
                    count_aprovado += 1
                    
        print(f"Filtro concluído! Total lido: {count_total} | Aprovados (ICP): {count_aprovado}")
        print(f"Arquivo salvo em: {output_file}")
        
    except Exception as e:
        print(f"Erro ao processar: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Script de filtro de ICP")
    print("Para uso real, execute importando ou ajustando os caminhos dos arquivos abaixo.")
    # Exemplo de uso:
    # filter_prospects('leads_brutos.csv', 'leads_filtrados_nordeste.csv')
