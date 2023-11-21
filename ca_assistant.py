from typing import Iterable, List

from ca_storage import CAStorage
from models.ca_assistant_answer import CAAssistantAnswer
from models.ca_document import CADocument
from rerankers import BaseRanker
from models.qaction import QAction

from testgpt import needs_conversational_response, give_conversational_response

Response = tuple[str, List[CADocument]]

RERANKERS_SCORE_THRESHOLD = 250
DOCUMENTS_TO_RETURN = 4 


class CAAssistantModel:
    def __init__(self, query_actions: Iterable[QAction],  documents_rerankers: Iterable[BaseRanker] ):
        self.query_actions = query_actions
        self.documents_rerankers = documents_rerankers

        self.storage = CAStorage()
        self.docs_no = self.storage.docs_embeddings_collection.count()
        #self.storage.reset_query_cache()
        
    def alter_doc_score(self, query: str, doc_id: str, alteration: int):
        self.storage.drm.alter_score_by(query, doc_id, alteration)
        

    def query(self, user_query : str ) -> CAAssistantAnswer:
        assistant_output : CAAssistantAnswer = None # will be valorized later, or call assert False if it is none when returning.
        
        print("== Starting assistant == ")        
        
        # Step 1: Applying all queries actions
        
        queries = self._apply_query_actions(user_query)
        # Step 2: Check if query is already cached
        cached_query = self._check_for_cached_query(queries)

    
        if cached_query: 
            # Step 3.0: There is a query already cached. I can simply print the saved results
            type, response = self.storage.drm.retrieve_by(cached_query)  

            if type == None and response == None:
                return CAAssistantAnswer(cached_query, [])
            
            if type == "conversational": # response is "str"
                output = [CADocument.from_(conversational_response=response)]

            elif type == "documents":  # response is [ doc_id, likeness_score]
                print(response)
                response.sort(key=lambda x: x[1], reverse=True)  
                print("ordered")
                print(response)
                output = [ self.storage.get_document_from_id(doc_id) for doc_id, _ in response ] 

            assistant_output = CAAssistantAnswer(cached_query, output)
 
        else:
            # Step 3.1: Query is not cached. I must continue with the model
            print("== Starting documents ranking == ")
            
    
            # Doing so, we can use the ensemble logic even if the query has only one sentece, reducing the code lenght 
            # even if we lose a little of performance
       
            to_ask_query = queries[0]
            to_ask_documents = []

            print(" == Starting with esemble logic == ")
            outputs: list[list[CADocument]] = []
            for query in queries:
                print(f"For {query=}")
                self.storage.add_query_to_cache(query)  # Caching the query, will later save the response.
                support_output = self._ranking_process(query)
                outputs.append(support_output[:DOCUMENTS_TO_RETURN])
                print( *[d.brief() for d in support_output[:DOCUMENTS_TO_RETURN]], sep="\n" )
                print("\n\n")
            
            
            ordered_docs = self._compute_score_occurences(outputs)
            
            ordered_docs = [doc for doc in ordered_docs if doc.metadata["ReRankersScore"] > 250] 
            
            print(*[doc.brief_with_metadata() for doc in ordered_docs])
        
            #### NO DOCS FOUND HANDLE ####
            if not ordered_docs:
                print("NO DOCS FOUND!!")
                return CAAssistantAnswer(to_ask_query, [])
        
            to_ask_documents = ordered_docs[:DOCUMENTS_TO_RETURN]
            print("Asking to translate:", to_ask_query)
          
            x = needs_conversational_response(to_ask_query)
            print("needs conversational?", x)
            if x:
                conv_resp = give_conversational_response(to_ask_query,
                                                        str([doc.content for doc in to_ask_documents]))
                for query in queries:
                    try:
                        self.storage.drm.add_conv_response(to_ask_query, conv_resp)
                    except:
                        pass #crashes if it breaks the UNIQUE CONSTRAINT.
                
                output = [CADocument.from_(conversational_response=conv_resp)]
            else:
                ids = [doc.id for doc in to_ask_documents]
                for query in queries:
                    self.storage.add_query_to_cache(query)
                    self.storage.drm.add(query, ids)
                    print(f"Added {query}, {ids = } to cache")

                output = to_ask_documents
            
            assistant_output = CAAssistantAnswer(to_ask_query, output)
            assert assistant_output.query and assistant_output.documents, "Somehow Assistant Output Response is empty."
        return assistant_output
    

    def _ranking_process(self, query : str) -> list[CADocument]:

        def __semantic_search(query: str):
            top_k_results: CADocument = self.storage.ask_documentation(query, self.storage.docs_embeddings_collection.count())      
            assert (len_top_k := len(top_k_results)) > 0, "No results found. Assure your embeddings are generated."
            assert top_k_results[0] != top_k_results[1], """
            There are chunks duplicates.  
            Please regenerate your embeddings and make sure there are no running instances of streamlit while doing so."""
            for index, document in enumerate(top_k_results):
                _score = 5 * (len_top_k-index-1)
                document.metadata["SemanticResearchRank"] = _score
                document.metadata["ReRankersScore"] = _score

            return top_k_results
        
        def __apply_rerankers(query: str, documents):
            for ranker in self.documents_rerankers:
            #  print(f"\n--Before reranker {ranker}", *[d.brief_with_metadata() for d in documents[:15]], sep="\n" )
                documents = ranker.rank_action(query, documents) 
            #  print(f"\n--After reranker {ranker}",*[d.brief_with_metadata() for d in documents[:15]], sep="\n" )

            documents.sort(key=lambda x: x.metadata["ReRankersScore"], reverse=True)
            return documents
    
        top_documents = __semantic_search(query)
        return __apply_rerankers(query, top_documents)
    
       


    def _apply_query_actions(self, starting_query : str) -> list[str]:

        queries = [ starting_query ]
    
        for q_action in self.query_actions:
                query_data = []
                for query in queries:                   
                    query_data.extend( q_action.action.act( query ) )
                queries = query_data

        return list(set(queries))

    def _check_for_cached_query(self, queries : Iterable[str]):
        
        def __check(query):
            # print(f"Searching for '{query}' in the query cache.")
            if( cached_query := self.storage.ask_query_cache(query) ):
                print(f"{query = } is cached  => {cached_query = }")
            else:
                print(f"{query = } is not cached.")
            return cached_query
        
        # We search for every query. It can either be [query] or [q1, ..., qn] representing synonyms.
        for query in queries:
            cached_query = __check(query)
            if cached_query:
                break

        return cached_query
          
    def _compute_score_occurences(self, list_of_list : list[list[CADocument]]) -> list[CADocument]:
        docs_info = {}
        for sublist in list_of_list:
            for doc in sublist:
                if (_doc_id := doc.id) in docs_info:
                    # Aggiungi il ReRankersScore al punteggio esistente
                    docs_info[_doc_id]['ensemble_score'] += doc.metadata["ReRankersScore"]
                    docs_info[_doc_id]['occurrences'] += 1
                else:
                    # Crea una nuova voce nel dizionario per il documento
                    docs_info[_doc_id] = {
                        'ensemble_score': doc.metadata["ReRankersScore"],
                        'document': doc,
                        'occurrences': 1
                    }

        results = [(info['document'], info['ensemble_score'], info['occurrences']) for info in docs_info.values()]
        results.sort(key=lambda x: (x[2], x[1]), reverse=True)

        return [document for document, _, _ in results]
