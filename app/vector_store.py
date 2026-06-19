import os
import numpy as np
import faiss

from typing import List, Dict

from sentence_transformers import SentenceTransformer

from .db import get_session
from .models import TranscriptChunk


MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "all-MiniLM-L6-v2"
)


embedder = SentenceTransformer(
    MODEL_NAME
)


INDEX_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "faiss.index"
)


META_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "faiss_meta.npy"
)



def embed_texts(
    texts:List[str]
):

    return embedder.encode(
        texts,
        normalize_embeddings=True
    )




def load_meta():

    if not os.path.exists(META_FILE):

        return []


    return np.load(
        META_FILE,
        allow_pickle=True
    ).tolist()





def save_meta(meta):

    np.save(
        META_FILE,
        np.array(
            meta,
            dtype=object
        ),
        allow_pickle=True
    )





def add_meeting_chunks(
        meeting_id:int,
        title:str,
        chunks:List[str]
):


    vectors = embed_texts(
        chunks
    )


    dimension = vectors.shape[1]


    if os.path.exists(INDEX_FILE):

        index = faiss.read_index(
            INDEX_FILE
        )

    else:

        index = faiss.IndexFlatIP(
            dimension
        )



    index.add(
        vectors.astype(
            "float32"
        )
    )



    meta = load_meta()



    start = len(meta)



    for i,chunk in enumerate(chunks):

        meta.append(

            {
                "id":
                start+i,

                "meeting_id":
                meeting_id,

                "title":
                title,

                "text":
                chunk
            }

        )



    faiss.write_index(
        index,
        INDEX_FILE
    )


    save_meta(
        meta
    )




    with get_session() as s:


        pos=0


        for chunk in chunks:


            s.add(

                TranscriptChunk(

                    meeting_id=meeting_id,

                    text=chunk,

                    start_pos=pos

                )

            )


            pos += len(chunk)



        s.commit()







def search(
        query:str,
        top_k:int=5
):


    if not os.path.exists(INDEX_FILE):

        return []



    index = faiss.read_index(
        INDEX_FILE
    )


    query_vector = embed_texts(
        [query]
    )


    scores, ids = index.search(

        query_vector.astype(
            "float32"
        ),

        top_k

    )



    meta = load_meta()



    results=[]



    for score,idx in zip(
        scores[0],
        ids[0]
    ):


        if idx < 0:

            continue



        item = meta[idx]



        results.append(

    {

        "meeting_id":
        item.get("meeting_id"),


        "title":
        item.get(
            "title",
            "Unknown"
        ),


        "text":
        item.get(
            "text",
            ""
        ),


        "snippet":
        item.get(
            "text",
            ""
        ),


        "score":
        round(
            float(score),
            4
        )

    }

)



    return results