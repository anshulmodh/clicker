from flask import Flask, g, render_template, request, session, redirect, url_for
from flask_restful import Resource, Api, reqparse
from flask_pymongo import PyMongo
import json
import pymongo
import random
import string
import json
import bcrypt

app = Flask(__name__)

app.config['MONGO_DBNAME'] = 'clicker'                  # mongoDB authentication to be moved to config file and enconded
app.config['MONGO_URI'] = 'mongodb+srv://db:db@clicker-ancot.mongodb.net/clicker?retryWrites=true&w=majority'
api = Api(app)

mongo = PyMongo(app)

@app.route("/")
def index():                    # Default path open swagger API docs
  f = open("swagger.json", 'r')
  return json.load(f)

@app.route("/home")             # Homepage for registering and loggin in
def home():
    return render_template("home.html")

@app.route("/register", methods=['POST', 'GET'])        # Registering page, to be changed to Google Log in 
def register():
    if(request.method == 'POST'):   # Post request to register
        users = mongo.db.users
        findExisting = users.find_one({'name' : request.form['username']})
        if findExisting is None:
            hashpass = bcrypt.hashpw(request.form['pass'].encode('utf-8'), bcrypt.gensalt())  # Bcrypt hashing
            users.insert({'name' : request.form['username'], 'password' : hashpass})
            session['username'] = request.form['username']
            return redirect(url_for('index'))
        return 'That username already exists'
    return render_template('register.html')

@app.route("/poll")     # Answering page
def poll():
    return render_template("poll.html")

@app.route("/user")     # Professor Overview page
def user():
    return render_template("user.html")

@app.route("/classes")  # Classes display page
def classes():
    return render_template("classes.html")

@app.route("/client")   # Student main page
def client():
    return render_template("client.html")

def randomStringDigits(length):     # Code Generation for class ids 
    """Generate a random string of letters and digits """
    lettersAndDigits = string.ascii_letters + string.digits
    return ''.join(random.choice(lettersAndDigits) for i in range(length))

class createClass(Resource):        # Endpoint creates a class object in the db
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('user', required=True)
        parser.add_argument('className', required=True)
        args = parser.parse_args()
        return self.createNewClass(args)
        
    def createNewClass(self, args):
        username = args['user']
        className = args['className']
        code = self.getCode()
        if self.checkUserName(username):    # Check if username exists; add to existing user data or create new user
            if self.checkClass(username, className):
                return 400
            mongo.db.mapping.update_one({"_id": username},  {"$set": {"Classes." + code: className}})
            mongo.db.classes.insert_one({"_id":code, "user": username,"class": className, "answers": {}, "status":False})
            mongo.db.ids.update_one({"_id": 0}, {"$addToSet": {"ids": code}})
        else:
            mongo.db.mapping.insert_one({"_id": username, "Classes" : {code: className}})
            mongo.db.classes.insert_one({"_id":code, "user": username,"class": className, "answers": {}, "status":False})
            mongo.db.ids.update_one({"_id": 0}, {"$addToSet": {"ids": code}})
            mongo.db.ids.update_one({"_id": 0}, {"$addToSet": {"names": username}})
        return 200

    def checkUserName(self, username):      # Check if username exists
        ids = mongo.db.ids.find({"_id": 0})
        if username in ids[0]["names"]:
            return True
        else:
            return False
    
    def getCode(self):      # Retrieve code for class ids
        while True:
            code = randomStringDigits(10)
            ids = mongo.db.ids.find({"_id": 0})
            if code not in ids[0]["ids"]:
                return code

    def checkClass(self, username, name):       # Check if a class name exists in the db
        data = mongo.db.mapping.find_one({'_id': username})['Classes']
        for className in data.keys():
            if data.get(className) == name:
                return True
        return False

class deleteUser(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('user', required=True)
        args = parser.parse_args()
        return self.deleteUser(args['user'])

    def deleteUser(self, username):     # Delete the user entirely from the backend
        try:
            ids = mongo.db.mapping.find_one({"_id":username})['Classes']
            results = mongo.db.mapping.delete_one({"_id": username})
            results = mongo.db.classes.find({"user": username})
            for result in results:
                data = mongo.db.classes.delete_one({"_id": result['_id']})
            mongo.db.ids.update({"_id": 0}, {"$pull": {"names": username}})
            for tag in ids.keys():
                mongo.db.ids.update({"_id": 0}, {"$pull": {"ids": tag}})
        except Exception as e:
            return str(e)
        return 200

class deleteClass(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('user', required=True)
        parser.add_argument('className', required=True)
        args = parser.parse_args()
        return self.deleteClass(args['user'], args['className'])

    def deleteClass(self, username, className): # Delete a specific class from a user
        try:
            ids = mongo.db.mapping.find_one({"_id":username})['Classes']
            for tag in ids.keys():
                if ids.get(tag) == className:
                    targetId = tag
                    break
            mongo.db.mapping.update({"_id": username}, {"$unset": {"Classes." + str(targetId): ""}})
            results = mongo.db.classes.delete_one({"_id": targetId})
            mongo.db.ids.update({"_id": 0}, {"$pull": {"ids": targetId}})
        except Exception as e:
            return str(e)
        return 200

class pollStatus(Resource):     # Return or update the status of a poll given user and class data
    def get(self, user, className):
        try:
            targetId = self.getID(user, className)
            return str(mongo.db.classes.find_one({"_id": targetId})['status'])
        except Exception as e:
            return e

    def post(self, user, className):        # Update the status of the poll
        parser = reqparse.RequestParser()
        parser.add_argument('status', required=True)
        args = parser.parse_args()
        try:
            targetId = self.getID(user, className)
            mongo.db.classes.update({"_id": targetId}, {"$set": {"status": bool(args['status'] == "true")}})
            return mongo.db.classes.find_one({"_id": targetId})['status']
        except Exception as e:
            return str(e)

    def getID(self, user, className):       # Get the ID of a specific class
        ids = mongo.db.mapping.find_one({"_id":user})['Classes']
        targetId = None
        for tag in ids.keys():
            if ids.get(tag) == className:
                targetId = tag
                break
        return targetId

class answer(Resource):     # Answer a given poll if it is open
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('client', required=True)
        parser.add_argument('user', required=True)
        parser.add_argument('className', required=True)
        parser.add_argument('answer', required=True)
        args = parser.parse_args()
        targetId = pollStatus.getID(self, args['user'], args['className'])
        if mongo.db.classes.find_one({"_id": targetId})['status']:
            if args['client'] not in mongo.db.classes.find_one({"_id": targetId})['answers'].keys():
                mongo.db.classes.update_one({"_id": targetId}, {"$set": {"answers." + args['client']: args['answer']}})
                return 200
            return "name taken"
        return "not open"

class report(Resource):     # Return a dictionary of the answers collected
    def get(self, user, className):
        targetId = pollStatus.getID(self, user, className)
        try:
            classData = mongo.db.classes.find_one({"_id": targetId})
            if not classData['status']:
                return classData['answers']
            else:
                return "poll still open"
        except Exception as e:
            return str(e)

api.add_resource(createClass, '/createClass')
api.add_resource(deleteUser, '/deleteUser')
api.add_resource(deleteClass, '/deleteClass')
api.add_resource(pollStatus, '/pollStatus/<string:user>/<string:className>')
api.add_resource(answer, '/answer')
api.add_resource(report, '/report/<string:user>/<string:className>')