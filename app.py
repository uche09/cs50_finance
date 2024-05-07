import os

from cs50 import SQL
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"]) # Load user's info
    stocks = db.execute("SELECT * FROM user_stocks WHERE user_id = ?", session["user_id"]) # Load all user's stock
    grand_total = user[0]["cash"]

    for stock in stocks:
        stock_price = lookup(stock["symbol"]) # Get current price of all user stocks
        if not stock_price:
            return apology("Bad Network")
        
        # Calculate total value of each stock (stock current price * No of shares own)
        total_value = float(stock["total_shares"]) * stock_price["price"]

        stock["price"] = stock_price["price"]
        stock["total_value"] = total_value
        
        # Grand_total: Sum of total value of all user stocks + user's main balance
        grand_total += total_value

    return render_template("index.html", balance=f"${user[0]['cash']:.2f}", stocks=stocks,
                           grand_total=f"${grand_total:.2f}")



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # Get user info from database
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

    if request.method == "POST":

        if request.form.get("action") == "lookup": # if user look up stock price
            symbol = request.form.get("symbol")

            if not symbol:
                return apology("Symbol cannot be blank")
            
            symbol = lookup(symbol)

            if not symbol:
                return apology("Invalid Symbol")
            else:
                return render_template("buy.html", balance=f"${user[0]['cash']:.2f}", 
                                       symbol=symbol["symbol"], price=f"${symbol['price']}")
        

        
        elif request.form.get("action") == "buy": # if user initiates a purchase
            symbol = request.form.get("symbol")

            # Get user's local datetime and timezone
            date_time = request.form.get("datetime")
            timezone = request.form.get("timezone")
            

            # Validate user input
            if not symbol:
                return apology("Symbol cannot be blank")
            
            symbol = lookup(symbol)
            
            if not symbol:
                return apology("Invalid symbol")

            shares = request.form.get("shares")
            if not shares:
                return apology("You did not input the number or shares to buy")
            
            try: # make sure user input (shares) is digit
                shares = int(shares)
            except ValueError:
                return apology("No. of shares must be digits")
            
            if shares < 1:
                return apology("Minimum of 1 share allowed")
            

            # validate datetime input
            if not date_time or not timezone:
                flash("Allow timezone to load", "error")
                return render_template("buy.html", balance=f"${user[0]['cash']:.2f}",
                                       symbol=symbol["symbol"], price=f"${symbol['price']}")
            
            try: # make sure date/time input is in datetime format
                date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                flash("Do not change the date/time format", "error")
                return render_template("buy.html", balance=f"${user[0]['cash']:.2f}",
                                       symbol=symbol["symbol"], price=f"${symbol['price']}")
            
            # Total cost of purchased shares
            total_share_price = symbol["price"] * shares

            if user[0]["cash"] < total_share_price:
                return apology("Insufficient balance")
            

            # Add puchased stock to user's stocks
            stock = db.execute("SELECT * FROM user_stocks WHERE user_id = ? AND symbol = ?",
                               user[0]["id"], symbol["symbol"])
            
            if len(stock) == 1: # if symbol already exist, add new share to existing share
                stock[0]["total_shares"] += shares
                db.execute("UPDATE user_stocks SET total_shares = ? WHERE symbol = ?",
                           stock[0]["total_shares"], symbol["symbol"])
                
            elif len(stock) == 0: # if symbol does not already exist, insert as new symbol
                db.execute("INSERT INTO user_stocks (user_id, symbol, total_shares)" +
                           " VALUES(?, ?, ?)", user[0]["id"], symbol["symbol"], shares)
                
            else:
                flash("YOU HAVE A DUPLICATED STOCK!!", "error")
                return redirect("/")
            
            
            # Debit user's balance
            user[0]["cash"] -= total_share_price

            db.execute("UPDATE users SET cash = ? WHERE id = ?", user[0]["cash"], user[0]["id"])
            
            # save datetime object to database as string
            date_time = datetime.strftime(date_time, "%Y-%m-%d %H:%M:%S")

            # Save user's transaction
            db.execute("INSERT INTO stock_transactions (" +
                       "datetime, user_id, symbol, purch_price, num_shares, total_cost, timezone,"+
                       " transaction_type) VALUES(?,?,?,?,?,?,?,?)",
                       date_time, user[0]["id"], symbol["symbol"], symbol["price"], shares,
                        total_share_price, timezone, "buy")
            
            
            flash(f"{symbol['symbol']} purchase successful", "Success")
            return redirect("/buy")

    else:
        return render_template("buy.html", balance=f"${user[0]['cash']:.2f}")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM stock_transactions WHERE user_id = ? ORDER BY datetime DESC",
                            session["user_id"])
    
    # Change datetime format
    for transaction in history:
        date_time = datetime.strptime(transaction["datetime"], "%Y-%m-%d %H:%M:%S")
        date_time = datetime.strftime(date_time, "%d-%B-%Y %H:%M")

        transaction["datetime"] = date_time

    return render_template("history.html", history=history)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        symbol = request.form.get("symbol")

        response = lookup(symbol)

        if not response:
            flash("Encountered an error, pleace make sure you entered a valid symbol", "error")
            return redirect("/quote")
        else:
            return render_template("quoted.html", response=response)
        
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        username = request.form.get("username")

        if not username:
            return apology("Username cannot be vacant")
        
        user = db.execute("SELECT * FROM users WHERE username = ?", username)

        if len(user) > 0:
            return apology("Sorry this username has been taken.")
        
        
        
        if not request.form.get("password") or not request.form.get("confirmation"):
            # if either of the password input is empty
            return apology("Password or Confirm Password cannot be vacant")
        
        elif len(request.form.get("password")) < 8:
            return apology("Password must be at least 8 characters")
        
        elif not (request.form.get("password") == request.form.get("confirmation")):
            # if confirmation password is not the same
            return apology("Password and Confirm password does not match")
        
        password = generate_password_hash(request.form.get("password"))

        # Register user
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, password)

        # Log user in
        user = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = user[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        
        user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"]) # Get user info
        # Get user's local datetime and timezone
        date_time = request.form["datetime"]
        timezone = request.form["timezone"]

        # Validate user input
        symbol_to_sell = request.form.get("symbol")
        shares_to_sell = request.form.get("shares")

        if not symbol_to_sell:
            return apology("Please choose a symbol")
        
        # Get stock info in user's account
        stocks = db.execute("SELECT * FROM user_stocks WHERE symbol = ? AND user_id = ?", symbol_to_sell, session["user_id"])
        stock_price = lookup(symbol_to_sell)

        if not stock_price:
            return apology("Invalid Symbol or Bad netword")

        if not stocks or len(stocks) != 1: # If stock does not exist in user account
            return apology("You don't own any share on this stock")
        
        if not shares_to_sell:
            return apology("Enter No. of shares to sell")
        
        try:
            shares_to_sell = int(shares_to_sell)
        except ValueError:
            return apology("No of shares must be digit(s)")
        
        if shares_to_sell < 1:
            return apology("No. of shares cannot be less than 1")
        
        if stocks[0]["total_shares"] < shares_to_sell:
            return apology("Cannot sell above total shares own")
        
        
        income = float(shares_to_sell) * stock_price["price"]
        stocks[0]["total_shares"] -= shares_to_sell

        # validate datetime input
        if not date_time or not timezone:
            flash("Allow timezone to load", "error")
            return redirect("/sell")
        
        try: # make sure date/time input is in datetime format
            date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            flash("Do not change the date/time format", "error")
            return redirect("/sell")
        
        # Begin transaction
        db.execute("UPDATE users SET cash = ? WHERE id = ?", user[0]["cash"] + income,
                    session["user_id"])
        
        if stocks[0]["total_shares"] < 1: # If user sold all shares for this stock
            db.execute("DELETE FROM user_stocks WHERE symbol = ?", symbol_to_sell)
        else:
            db.execute("UPDATE user_stocks SET total_shares = ? WHERE symbol = ?",
                       stocks[0]["total_shares"], symbol_to_sell)
            

        # save datetime object to database as string
            date_time = datetime.strftime(date_time, "%Y-%m-%d %H:%M:%S")

        # Save user's transaction to user history
        db.execute("INSERT INTO stock_transactions (" +
                    "datetime, user_id, symbol, purch_price, num_shares, total_cost, timezone,"+
                    " transaction_type) VALUES(?,?,?,?,?,?,?,?)",
                    date_time, user[0]["id"], stock_price["symbol"], stock_price["price"], shares_to_sell,
                    income, timezone, "sell")
        
        flash(f"{symbol_to_sell} sold successfully", "Success")
            
        return redirect("/")

    else:
        stocks = db.execute("SELECT symbol FROM user_stocks WHERE user_id = ?", session["user_id"])
        return render_template("sell.html", stocks=stocks)
    


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():

    # Forget any user_id
    session.clear()

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        

        # Query database for username
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists
        if len(user) != 1:
            return apology("This username does not exist")
        
        
        # Ensure password meet requirment

        if not request.form.get("new-password") or not request.form.get("confirmation"):
            # if either of the password input is empty
            return apology("Password or Confirm Password cannot be vacant")
        
        elif len(request.form.get("new-password")) < 8:
            return apology("Password must be at least 8 characters")
        
        elif not (request.form.get("new-password") == request.form.get("confirmation")):
            # if confirmation password is not the same
            return apology("Password and Confirm password does not match")
        
        new_password = generate_password_hash(request.form.get("new-password"))

        # Update password
        db.execute("UPDATE users SET hash = ? WHERE username = ?", new_password,
                    request.form.get("username"))

        # Log user in
        user = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = user[0]["id"]

        return redirect("/")

    else:
        return render_template("reset_password.html")