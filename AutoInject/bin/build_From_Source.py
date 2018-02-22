import pymongo, re, time, datetime, os

# Parsing related modules
# import AutoInject.bin.patch_Handler as ph

import ply.lex                      as lex
from pygments                       import highlight
from pygments.lexers                import guess_lexer_for_filename, get_lexer_by_name
from pygments.styles                import get_all_styles, get_style_by_name
from pygments.formatters            import get_formatter_by_name
from shutil                         import copyfile
from pkg_resources                  import resource_filename

from pymongo                        import MongoClient
from json                           import loads
from bson.json_util                 import dumps

from subprocess                     import check_output, check_call
from copy                           import copy
from collections                    import defaultdict

client                              = MongoClient()
package_collection                  = client['package_db']['package_list']
cve_collection                      = client['cvedb']['cves']

kwargs  = {
    'java' : { 
        'compile' : 'y',
        'command' : 'javac'
    }
}
list_Of_Compiler_Procedures = defaultdict(dict, **kwargs)

def search_URL_For_BFS_Update():
    pass

def search_Files(file_name):
    path_to_script = resource_filename("AutoInject", "/bin/sudo_scripts/update_db")
    os.system(path_to_script)
    full_file_path = check_output(
        ["locate", file_name],
        universal_newlines=True
    )
    if (full_file_path[-1:] == "\n"): full_file_path = full_file_path[:-1]
    return full_file_path

def format_HTML(filepath):
    with open(filepath, 'r') as file_to_read:
        data            = file_to_read.read()
        lexer_object    = guess_lexer_for_filename(filepath, data)
        pyg_formatter   = get_formatter_by_name('html', linenos='table', style='monokai')
        completed       = highlight(data, lexer_object, pyg_formatter)
        return completed

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
#                           Lexer related functions                        |
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------

# Tokens for parsing code
tokens = (
    # SEMANTICS
    'NEWLINE',      'ADD_AFTER',    'ADD_REPLACE_ADDITION', 'ADD_REPLACE_REMOVE',
    # VARIABLES
    'NUMBER',       'VARIABLE',     'STRING',               'STRING2',
    # OPERATORS
    'S_EQUALS',     'D_EQUALS',
    'T_EQUALS',     'N_EQUALS',     'PLUS',                 'MINUS', 
    'DIVIDE',       'MULTIPLY',     'LPAREN',               'RPAREN', 
    'LT',           'LTOE',         'GT',                   'GTOE', 
    'S_LBRACE',     'LBRACE',       'S_RBRACE',             'RBRACE',
    'SEMICOLON',    'EOL',          'S_AND',                'L_AND', 
    'S_OR',         'L_OR',
)

# Regular expression rules 
# 1) VARIABLES
t_NUMBER                = r'[-+]?[0-9]*\.?[0-9]+'
t_VARIABLE              = r'[a-zA-Z][a-zA-Z0-9_]*'
t_STRING                = r'\"(.+?)\"'
t_STRING2               = r'\'(.+?)\''
# 2) OPERATORS
t_S_EQUALS              = r'='
t_D_EQUALS              = r'=='
t_T_EQUALS              = r'==='
t_N_EQUALS              = r'!='
t_PLUS                  = r'\+'
t_MINUS                 = r'-'
t_DIVIDE                = r'/'
t_MULTIPLY              = r'\*'
t_LT                    = r'<'
t_LTOE                  = r'<='
t_GT                    = r'>'
t_GTOE                  = r'<='
t_LPAREN                = r'\('
t_RPAREN                = r'\)'
t_S_LBRACE              = r'\['
t_LBRACE                = r'\{'
t_S_RBRACE              = r'\]'
t_RBRACE                = r'\}'
t_SEMICOLON             = r':'
t_S_AND                 = r'\&\&'
t_L_AND                 = r'\&'
t_S_OR                  = r'\|\|'
t_L_OR                  = r'\|'
# 3) SEMANTICS
t_NEWLINE               = r'\n'
t_EOL                   = r'\;'
t_ADD_AFTER             = r'\&\*'
t_ADD_REPLACE_ADDITION  = r'\&\+\+'
t_ADD_REPLACE_REMOVE    = r'\&--'

# Ignore characters
t_ignore                = ' \t\r'

# Error catching
def t_error(t):
    print("Illegal character '%s'" % t.value)
    t.lexer.skip(1)

lexer_for_addition  = lex.lex(reflags=re.S)
lexer_for_file      = lex.lex(reflags=re.S)

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
#                           BFS related functions                          |
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------

def perform_File_Alterations(path_of_file_to_modify, path_of_new_file, bfs_string):
    
    if perform_Additions(path_of_file_to_modify, path_of_new_file, bfs_string):
        with open(path_of_new_file, 'w') as destination: 
            new_string = ""
            with open(path_of_new_file, 'r') as read_file:
                for lines in read_file:
                    new_string += lines.replace("    ", "\t")
                destination.write(new_string)
    else: print("Alterations failed"); return False

def perform_Additions(path_of_file_to_modify, path_of_file_to_write, additions):
    
    split_Additions             = additions.split("&*&")
    list_Of_Insertion_Tuples    = []

    for addition_Strings in split_Additions:
        
        addition_Strings = "\n" + addition_Strings + "\n"

        lexer_for_addition.input(addition_Strings) 

        if (os.path.exists(path_of_file_to_modify)): 
            tuple_Array = get_Tuples_For_Addition(path_of_file_to_modify, lexer_for_addition, addition_Strings)
        else: return False

        if tuple_Array: list_Of_Insertion_Tuples.extend(tuple_Array)
        else:           return False 

    if list_Of_Insertion_Tuples: 
        run_Addition_Searches(
            path_of_file_to_modify, 
            path_of_file_to_write, 
            list_Of_Insertion_Tuples
        )  
        print(list_Of_Insertion_Tuples)
    else:   
        print("No additions to add"); return False

def get_Tuples_For_Addition(path_of_file_to_modify, lexer_for_addition, addition_string):

    list_Of_Insertion_Tuples    = []

    with open(path_of_file_to_modify, 'r') as file_to_modify:
        
        data            = file_to_modify.read()
        lexer_for_file.input(data)
        
        file_token      = lexer_for_file.token()
        addition_token  = lexer_for_addition.token()
        loop            = True
        start_pos       = file_token.lexpos
        end_pos         = file_token.lexpos
        point_to_insert = 0

        while loop:

            copy_of_lexer_for_file      = copy(lexer_for_file)
            copy_of_token_for_file      = file_token

            if (not addition_token or not copy_of_token_for_file): break

            start_line                  = file_token.lexpos
            matched                     = False

            if (addition_token.type == 'ADD_AFTER'):

                try:    addition_token  = lexer_for_addition.token()
                except: return False
                
                copy_of_lexer_for_addition  = copy(lexer_for_addition) 
                copy_of_addition_token      = addition_token

                while (copy_of_token_for_file != None and matched == False):
                    # Matching the start of the addition lexer start to the lexer for the file token
                    print("Before File token:", file_token.value, "Before Addition copy:", copy_of_addition_token.value)
                    while (file_token.value != copy_of_addition_token.value): 
                        try:    
                            file_token = lexer_for_file.token()
                            if not file_token: return False
                            print("File token:", file_token.value, "Addition copy:", copy_of_addition_token.value)
                        except: return False

                    copy_of_lexer_for_addition  = copy(lexer_for_addition)
                    copy_of_addition_token      = addition_token

                    copy_of_lexer_for_file      = copy(lexer_for_file)
                    copy_of_token_for_file      = file_token

                    while (copy_of_token_for_file != None and copy_of_addition_token != None 
                        and copy_of_addition_token.value == copy_of_token_for_file.value and matched == False):

                        if not matched:
                            try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                            except: return False

                            try:    
                                tmp                     = copy_of_token_for_file
                                copy_of_token_for_file  = copy_of_lexer_for_file.token()
                            except: return False

                        if (copy_of_addition_token.type == 'NEWLINE'):
                            
                            start_pos = copy_of_addition_token.lexpos

                            try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                            except: return list_Of_Insertion_Tuples

                            while (addition_token.lexpos != copy_of_addition_token.lexpos):
                                addition_token = lexer_for_addition.token()
                            
                            if copy_of_token_for_file:
                                # Getting the token for the file in line with the copy that has matched
                                while (file_token.lexpos != copy_of_token_for_file.lexpos):
                                    file_token = lexer_for_file.token()
                            else:
                                # Getting the token for the file in line with the copy that has matched
                                while (file_token.lexpos != tmp.lexpos):
                                    file_token = lexer_for_file.token()

                            matched = True
                            break

                    if not matched: 
                        try:    
                            file_token              = lexer_for_file.token()
                            copy_of_addition_token  = addition_token
                        except: return False

                print("Done with finding area to append at")
                if file_token: point_to_insert = file_token.lexpos + 1

            elif (addition_token.type == 'ADD_REPLACE_REMOVE'):
                
                print("Found add replace remove")

                try:    addition_token  = lexer_for_addition.token()
                except: return False

                matched = False
                while not matched:    

                    copy_of_lexer_for_addition  = copy(lexer_for_addition)
                    copy_of_addition_token      = addition_token
                    
                    while (file_token.value != copy_of_addition_token.value): 
                        try:    
                            file_token = lexer_for_file.token()
                            if not file_token: return False
                        except: return False

                    start_position_to_remove    = file_token.lexpos
                    copy_of_lexer_for_file      = copy(lexer_for_file)
                    copy_of_token_for_file      = file_token

                    while (copy_of_token_for_file != None and copy_of_addition_token != None 
                        and copy_of_token_for_file.value == copy_of_addition_token.value and matched == False):

                        if not matched:
                            try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                            except: return False

                            try:    
                                tmp                     = copy_of_token_for_file
                                copy_of_token_for_file  = copy_of_lexer_for_file.token()
                            except: return False

                        if (copy_of_addition_token.type == 'NEWLINE'):
                            
                            try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                            except: return list_Of_Insertion_Tuples

                            while (addition_token.lexpos != copy_of_addition_token.lexpos):
                                addition_token = lexer_for_addition.token()
                            
                            if copy_of_token_for_file:
                                while (file_token.lexpos != copy_of_token_for_file.lexpos):
                                    file_token = lexer_for_file.token()
                            else:
                                while (file_token.lexpos != tmp.lexpos):
                                    file_token = lexer_for_file.token()
                            
                            end_position_to_remove = file_token.lexpos
                            matched = True
                    
                    if not matched: 
                        try:    
                            file_token              = lexer_for_file.token()
                            copy_of_addition_token  = addition_token
                        except: return False

                if (copy_of_addition_token.type == 'NEWLINE'): 
                    
                    try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                    except: return False

                    while (addition_token.lexpos != copy_of_addition_token.lexpos):
                        try:    addition_token = lexer_for_addition.token()
                        except: return False

                if (copy_of_addition_token.type == 'ADD_REPLACE_ADDITION'):    
                        
                        start_pos = copy_of_addition_token.lexpos + len(copy_of_addition_token.value)

                        try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                        except: return False

                        while (copy_of_addition_token.type != 'NEWLINE'):
                            try:    copy_of_addition_token = copy_of_lexer_for_addition.token()
                            except: return False
                        
                        string_to_add   = ""
                        end_pos         = copy_of_addition_token.lexpos + len(copy_of_addition_token.value) - 1
                        count           = 0

                        for characters in addition_string:
                            if (start_pos <= count <= end_pos):
                                string_to_add   += characters
                            count           += 1
                        
                        list_Of_Insertion_Tuples.append((start_position_to_remove, end_position_to_remove, string_to_add))
                        print(list_Of_Insertion_Tuples)

                        while (addition_token.lexpos != copy_of_addition_token.lexpos):
                            try:    addition_token = lexer_for_addition.token()
                            except: return False

                        matched = True

                if file_token: point_to_insert = file_token.lexpos

                start_pos = addition_token.lexpos
            
            elif (addition_token.type == 'NEWLINE'):
                print("Found newline")
                if addition_token: start_pos = addition_token.lexpos
                try:    addition_token = lexer_for_addition.token()
                except: print("No token after Newline"); return list_Of_Insertion_Tuples
            
            # Standard addition
            else: 
                while (addition_token != None and addition_token.type != 'NEWLINE'):
                    try:    addition_token = lexer_for_addition.token()
                    except: end_pos = addition_token.lexpos

                string_to_add   = ""
                if addition_token: print("End pos:", addition_token); end_pos = addition_token.lexpos
                count           = 0

                for characters in addition_string:
                    if (start_pos + 1 <= count <= end_pos):
                        string_to_add   += characters
                        count           += 1
                    else: count += 1

                if addition_token: start_pos = addition_token.lexpos

                list_Of_Insertion_Tuples.append((point_to_insert, string_to_add)) 
                print("Current status:", list_Of_Insertion_Tuples)

    print("Retuning:", list_Of_Insertion_Tuples)
    return list_Of_Insertion_Tuples

def run_Addition_Searches(path_of_file_to_modify, path_of_file_to_write, list_Of_Insertion_Tuples):
    
    string_for_file = ""
    count_of_characters = 0
    print("List to use:", list_Of_Insertion_Tuples)

    if (os.path.exists(path_of_file_to_modify)):   
        with open(path_of_file_to_modify, 'r') as file_to_modify:
            for characters in file_to_modify.read():  
                added = False 
                for tuples in list_Of_Insertion_Tuples:
                    if (type(tuples[1]) is int):
                        if (tuples[1] == count_of_characters): 
                            print("Adding at:", count_of_characters)
                            if tuples[2] != "\n": string_for_file += tuples[2] 
                        elif (tuples[0] <= count_of_characters <= tuples[1]): added = True
                    elif (tuples[0] == count_of_characters): string_for_file += tuples[1]
                    
                if not added: string_for_file += characters; added = True
                count_of_characters += 1
        # Account for if addition at the end of the file
        with open(path_of_file_to_modify, 'r') as file_to_modify:        
            for tuples in list_Of_Insertion_Tuples:
                if not (type(tuples[1]) is int):
                    if (tuples[0] == len(file_to_modify.read())):
                        string_for_file += '\n' + tuples[1]
    
    else: print("Path does not exist to file")

    with open(path_of_file_to_write, 'w') as file_to_write:
        file_to_write.write(string_for_file)

example_Patch = '''
&* class adder:
&* def hello():
&-- return "Hello"
&++ hi
hi
hlrlo
ffrfr
'''

print(perform_Additions('../file_store/test/patch_file.py', '../file_store/test/patch_file.patch', example_Patch))
