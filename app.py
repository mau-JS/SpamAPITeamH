from flask import Flask, request, jsonify
import pickle
import category_encoders as ce
import numpy as np
import pandas as pd
from email.utils import parseaddr
import re
import io
import emoji
from wordcloud import WordCloud
from sklearn.ensemble import RandomForestClassifier
from nltk.corpus import PlaintextCorpusReader, stopwords, wordnet as wn
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.stem import WordNetLemmatizer, PorterStemmer
from gensim.models import word2vec
from nltk.probability import FreqDist
from nltk.collocations import BigramCollocationFinder, TrigramCollocationFinder
from nltk.metrics import BigramAssocMeasures, TrigramAssocMeasures
import nltk
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')
#comment

app = Flask(__name__)

with open('word2vec_model.pkl', 'rb') as f:
    w2v = pickle.load(f)

with open('random_forest_model.pkl', 'rb') as model_file:
    random_forest_model = pickle.load(model_file)


# Load the TLD_Freq data from the CSV file
tld_data = pd.read_csv('tld_data_selected.csv')

###################################################
#Natural Language Preprocessing functions
def stopwordslist(languages):
    stop_list = []
    for i in languages:
        stop_list.extend(stopwords.words(i))
        #print("stop words",i)
    return stop_list
    
def tokenize_text(text):
    return word_tokenize(text)

def frequency_distance(tokens):
    fdist = nltk.FreqDist(tokens)
    return fdist

def frequency_tokens(tokens, fdist):
    dictionary = dict(fdist)
    frequency_df = pd.DataFrame.from_dict(
        dictionary,
        orient='index',
        columns=['Frequency']
    )
    frequency_df = frequency_df.sort_values(by=['Frequency'], ascending=False)
    frequency_df.index_name = 'Word'
    return frequency_df
    
def bigram_relation(fdist, tokens):
    bigram_measures = nltk.collocations.BigramAssocMeasures()
    bigram_fd = nltk.FreqDist(nltk.bigrams(tokens))
    finder = BigramCollocationFinder(fdist,bigram_fd)
    scored = finder.score_ngrams(bigram_measures.raw_freq)
    bigram_df = pd.DataFrame(scored, columns=['Bigram','Score'])
    bigram_df.sort_values(by='Score',ascending=False)
    return bigram_df
    
def word_cloud(df):
    if df.empty:
        print("No valid data for word cloud.")
        return
    text_dict = df.to_dict()['Frequency']
    wordcloud = WordCloud(background_color='white').generate_from_frequencies(text_dict)
    plt.figure()
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis("off")
    plt.show()

def cleaning(tokens):
    clean_list = []
    for i in tokens:
        if i.isalpha():
            clean_list.append(i.lower())
        elif emoji.is_emoji(i):
            clean_list.append(i)
    return clean_list

def delete_stopwords(cleaned, stop_words):
    filtered_words = [token for token in cleaned if token not in stop_words]
    return filtered_words
    
def lemmatize(tokens):
    ps = PorterStemmer()
    lemmatize_stem = [wn.morphy(token.lower()) or ps.stem(token.lower()) for token in tokens]
    return lemmatize_stem

def get_vector(tokens,model):
    vectors = []
    for i in tokens:
        if i in model.wv:
            vectors.append(model.wv[i])
    if vectors:
        return sum(vectors) / len(vectors)
    else:
        return [0] * model.vector_size

def apply_get_vector(tokens_list, model):
    vector_list = []
    for i in tokens_list:
        vector = get_vector(i, model)
        vector_list.append(vector)
    return vector_list



###################################################
def preprocess_data(data):
    # Extract features from the data dictionary
    attachment_count = data['Attachment Count']
    attachment_extensions = data['Attachment Extension']  # Keep it as a raw string
    email_subject = data['Email Subject']

    try:
        attachment_count = int(attachment_count)
    except ValueError:
        attachment_count = 0  # Set to 0 if not a valid integer

    # Extract TLD from email addresses
    def extract_tld(email):
        email = email.replace('"', '')  # Remove double quotes
        _, address = parseaddr(email)
        domain = address.split('@')[-1] if '@' in address else ''
        tld = domain.split('.')[-1] if domain else ''
        return tld

    email_from = data.get('Email From', '')  # Handle missing 'Email From' gracefully
    tld = extract_tld(email_from)
    
    matching_rows = tld_data[tld_data['TLD'] == tld]

    if not matching_rows.empty:
        tld_freq = matching_rows['TLD_Freq'].values[0]
    else:
    # TLD not found, replace with the median frequency
        median_tld_freq = 0.07764940472699548
        tld_freq = median_tld_freq

    # Calculate the length of the email address
    email_from_length = len(email_from)
    spam = 'Spam'
    df_api = pd.DataFrame({
        'Attachment Count': [attachment_count],
        'Email Subject': [email_subject],
        'closeNotes':[spam],
        'Email_From_Length': [email_from_length],
        'TLD_Freq': [tld_freq]
    })

    pd.set_option('display.max_columns', None)
    # Display the merged DataFrame
    #print(merged_df)
    # Apply binary encoding to the 'Attachment Extension'
    df_encoded = df_api[['Attachment Count','Email Subject','Email_From_Length','TLD_Freq']]
    df = df_encoded

    #ALL CORRECT BEFORE THIS
####################################################
    #Natural Language Preprocessing for Email Subject
    corpus_subject = df_encoded['Email Subject']
    languages = ['arabic', 'azerbaijani', 'basque', 'bengali', 'catalan', 'chinese', 'danish', 'dutch', 'english', 'finnish', 'french', 'german', 'greek',
                 'hebrew', 'hinglish', 'hungarian', 'indonesian', 'italian', 'kazakh', 'nepali', 'norwegian', 'portuguese', 'romanian', 'russian', 'slovene',
                 'spanish', 'swedish', 'tajik', 'turkish']
    stopW = stopwordslist(languages)
    corpus_subject = corpus_subject.astype(str)
    tokens = corpus_subject.apply(tokenize_text)
  
    
    df_frequency= []
    frequency_original = []
    for i in tokens:
        frequency_original = frequency_distance(i)
        frequency = frequency_tokens(i,frequency_original)
        df_frequency.append(frequency)
        
    bigrams = []
    for i in tokens:
        frequency_original = frequency_distance(i)
        bigram_get = bigram_relation(frequency_original, i)
        bigrams.append(bigram_get)
        
#####Corpus Processing
    cleaned = []
    for i in tokens:
        cleaned.append(cleaning(i))
        
    filtered_cleaned = []
    for i in cleaned:
        filtered_cleaned.append(delete_stopwords(i,stopW))

    lematized = []
    for i in filtered_cleaned:
        lematized.append(lemmatize(i))

    frequency_cleaned = []
    df_frequency_cleaned = []
    for i in lematized:
        frequency_cleaned = frequency_distance(i)
        frequency = frequency_tokens(i, frequency_cleaned)
        df_frequency_cleaned.append(frequency)

    bigrams_cleaned = []
    for i in lematized:
        frequency_cleaned = frequency_distance(i)
        bigram_get = bigram_relation(frequency_cleaned,i)
        bigrams_cleaned.append(bigram_get)


    #####Corpus Extraction
    size_vector = 100
    context_max = 35
    min_presence = 1
    epochs = 50

    unique_token = []
    for i in lematized:
        unique_token.extend(i)

    vectors = apply_get_vector(lematized, w2v)

    lematized_df = pd.DataFrame({'lematized': lematized})
    corpus_subject.reset_index(drop=True, inplace=True)
    corpus_subject = pd.concat([corpus_subject, lematized_df], axis=1)

    
    
    if(len(vectors) > len(lematized)):
        vectors = vectors[:1]
    corpus_subject['vectors'] = vectors


    df_encoded = df.join(corpus_subject['vectors'].set_axis(df.index))
    #print(df_encoded)

    # Replace 'df' with your DataFrame name
    df_encoded = df_encoded.drop('Email Subject', axis = 1)


    # Assuming 'vectors' contains embedding vectors
    n_components = len(df_encoded['vectors'][0])  # Get the number of components
    # Create a DataFrame with separate columns for each component
    embedding_columns = pd.DataFrame(df_encoded['vectors'].tolist(), columns=[f'embedding_component_{i}' for i in range(n_components)])
    # Concatenate the new columns with the original dataframe
    df_encoded = pd.concat([df_encoded, embedding_columns], axis=1)
    # Drop the original 'vectors' column
    df_encoded.drop(columns=['vectors'], inplace=True)
    return df_encoded


def preprocess_to_dict(df_encoded):
    return {'Preprocessed data': df_encoded.to_dict(orient = 'records')}

def obtain_predictions(df_encoded):
    predictions = random_forest_model.predict(df_encoded)
    return predictions
    
def obtain_probs(df_encoded):
    predictions_probs = random_forest_model.predict_proba(df_encoded)
    return predictions_probs
    
def calculate_majority_vote(predictions):
    # Assuming binary predictions (0 or 1)
    # Calculate the count of each prediction
    counts = pd.Series(predictions).value_counts()
    # Get the most frequent prediction (majority vote)
    majority_vote = counts.idxmax()

    return majority_vote
#Change
@app.route('/preprocess', methods=['POST'])  # Changed route to /preprocess
def preprocess():
    try:
        # Get data from POST request
        data = request.get_json()
        df = preprocess_data(data['features'])
        # Preprocess the data
        
        preprocessed_features = preprocess_to_dict(df)

        # Return preprocessed features (no prediction)
        return jsonify({'preprocessed_features': preprocessed_features})

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/predict', methods=['POST'])
def predict():
    try:
        # Get data from POST request
        data = request.get_json()
        df = preprocess_data(data['features'])
        predictions = obtain_predictions(df)
        return jsonify({'predictions': predictions.tolist()})

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/predict_prob', methods=['POST'])
def predict_probs():
    try:
        # Get data from POST request
        data = request.get_json()
        df = preprocess_data(data['features'])  # Replace with your preprocessing logic
        predictions_probs = obtain_probs(df)

        # Determine the winning class (highest probability)
        winning_class = int(predictions_probs.argmax(axis=1)[0])
        winning_prob = float(predictions_probs.max(axis=1)[0])

        return jsonify({
            'winning_class': winning_class,
            'winning_prob': winning_prob
        })

    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/predict_prob_from_csv', methods=['POST'])
def predict_prob_from_csv():
    try:
        # Get the uploaded file from the request
        file = request.files['file']
        
        # Read the CSV file into a DataFrame
        df = pd.read_csv(io.StringIO(file.stream.read().decode('utf-8')))
        
        # Preprocess each row in the DataFrame
        results = []
        for _, row in df.iterrows():
            features = row.to_dict()
            preprocessed_df = preprocess_data(features)  
            predictions_probs = obtain_probs(preprocessed_df)

            # Determine the winning class and its probability
            winning_class = int(predictions_probs.argmax(axis=1)[0])
            winning_prob = float(predictions_probs.max(axis=1)[0])

            results.append({
                'features': features,
                'winning_class': winning_class,
                'winning_prob': winning_prob
            })

        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
        
if __name__ == "__main__":
    app.run(debug=True)