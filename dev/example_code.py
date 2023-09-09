from ib111 import week_01

def is_a(ch):
    if ch == "a" or ch == "A":
        return True
    else:
        return False
  

def count_a(text):
    a=0
    for i in range(len(text)):
        if is_a(text[i]):
            a=a+1
    return a





